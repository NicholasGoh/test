# AUTOGENERATED! DO NOT EDIT! File to edit: 05_classifier_utils.ipynb (unless otherwise specified).

__all__ = ['PlotLosses', 'Classifier', 'GradCAM']

# Cell
import tensorflow as tf

class PlotLosses(tf.keras.callbacks.Callback):
    def on_train_begin(self, logs={}):
        self.i = 0
        self.x = []
        self.losses = []
        self.val_losses = []
        self.fig = plt.figure()
        self.logs = []
    def on_epoch_end(self, epoch, logs={}):
        self.logs.append(logs)
        self.x.append(self.i)
        self.losses.append(logs.get('loss'))
        self.val_losses.append(logs.get('val_loss'))
        self.i += 1
        IPython.display.clear_output(wait=True)
        plt.plot(self.x, self.losses, label="loss")
        plt.plot(self.x, self.val_losses, label="val_loss")
        plt.legend()
        plt.show()

# Cell
import cv2, os, telegram_send, tqdm, skimage, IPython, h5py, shutil
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
plt.style.use('seaborn-white')
from tensorflow.keras import layers
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.applications.mobilenet import MobileNet
import asl_detection.save

class Classifier:
    def __init__(self):
        self.categories = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        self.category_map = {i: v for i, v in enumerate(self.categories)}
        self.num_classes = len(self.categories)
        self.img_size = 224
        self.batch_size = 64

        self.train_path, self.test_path = None, None
        self.train_generator, self.test_generator = None, None
        self.step_size_train, self.step_size_valid = None, None
        self.images, self.labels = None, None
        self.classifier = None
        self.history = None
        self.grad_cam_names = None
        self.save_folder = None

        self.feature_extractor = None
        self.latent_vectors = None
        self.latent_path = None
        self.latent_test = None
        self.latent_train = None


    def generate_data(self, train_path, test_path, batch_size, figsize=(10,10), fontsize=16):
        self.train_path = train_path
        self.test_path = test_path
        self.batch_size = batch_size

        test_datagen = ImageDataGenerator(
                rescale=1/255.)
        train_datagen = ImageDataGenerator(
                rescale=1/255.,
                brightness_range=[.9, 1.],
                rotation_range=5,
                zoom_range=.1,
                width_shift_range=.1,
                height_shift_range=.1)
        self.train_generator = train_datagen.flow_from_directory(
                self.train_path,
                shuffle=True,
                target_size=(self.img_size, self.img_size),
                color_mode='rgb',
                batch_size=batch_size,
                seed=0,
                class_mode="categorical")
        self.test_generator = test_datagen.flow_from_directory(
                self.test_path,
                shuffle=True,
                target_size=(self.img_size, self.img_size),
                color_mode='rgb',
                batch_size=batch_size,
                seed=0,
                class_mode="categorical")

        _, axes = plt.subplots(6, 6, figsize=figsize)
        for i, category in enumerate(self.categories[:6]):
            path = self.train_path + '/' + category
            images = os.listdir(path)
            for j in range(6):
                image = cv2.imread(path + '/' + images[j])
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                axes[i, j].imshow(image)
                axes[i, j].set(xticks=[], yticks=[])
                axes[i, j].set_title(category, color = 'tomato').set_size(fontsize)
        plt.suptitle('Vanilla Data').set_size(2*fontsize)
        plt.tight_layout()

        images, labels = self.train_generator.next()
        _, axes = plt.subplots(6, 6, figsize=figsize)
        for i in range(6):
            for j in range(6):
                image = images[i+j]
                label = self.category_map[np.argmax(labels[i+j])]
                axes[i, j].imshow(image)
                axes[i, j].set(xticks=[], yticks=[])
                axes[i, j].set_title(label, color = 'tomato').set_size(fontsize)
        plt.suptitle('Augmented Data').set_size(2*fontsize)
        plt.tight_layout()

        self.step_size_train=int(self.train_generator.n // self.train_generator.batch_size)
        self.step_size_valid=int(self.test_generator.n // self.test_generator.batch_size)

    def notify(self, fig):
        fig.savefig('tmp.jpg')
        with open('tmp.jpg', 'rb') as f:
            telegram_send.send(images=[f])
        os.remove('tmp.jpg')

    def plot_accuracy(self, history):
        f, axes = plt.subplots(1, 2, figsize=(12, 4))
        accuracy = history.history['accuracy']
        loss = history.history['loss']
        val_accuracy = history.history['val_accuracy']
        val_loss = history.history['val_loss']
        print('Training accuracy: {:.{}f}'.format(np.max(accuracy), 3))
        print('Training loss: {:.{}f}'.format(np.max(loss), 3))
        print('Validation accuracy: {:.{}f}'.format(np.max(val_accuracy), 3))
        print('Validation loss: {:.{}f}'.format(np.max(val_loss), 3))
        axes[0].plot(history.history['accuracy'])
        axes[0].plot(history.history['val_accuracy'])
        axes[0].set_title('Model accuracy')
        axes[0].set(ylabel = 'accuracy', xlabel = 'Epoch')
        axes[0].legend(['Train', 'Test'], loc='upper left')
        axes[1].plot(history.history['loss'])
        axes[1].plot(history.history['val_loss'])
        axes[1].set_title('Model loss')
        axes[1].set(ylabel = 'Loss', xlabel = 'Epoch')
        axes[1].legend(['Train', 'Test'], loc='upper left')
        return f

    def set_feature_extractor(self, name = 'mobilenet', summary = False):
        if name == 'mobilenet':
            self.feature_extractor = MobileNet(input_shape = (self.img_size, self.img_size, 3), include_top=True,weights ='imagenet')
            output = self.feature_extractor.layers[-6].output
            self.feature_extractor = tf.keras.Model(self.feature_extractor.inputs, output)
        if summary:
            self.feature_extractor.summary()

    def extract_and_save(self, latent_path, latent_vectors, save=True):
        '''model: Model used to extract encoded features
           generator: yields (x_batch, y_batch)
        '''
        self.latent_vectors = latent_vectors
        self.latent_path = latent_path
        if not save:
            return
        for folder in ['train', 'test']:
            save_path = os.path.join(latent_path, folder)
            if os.path.exists(save_path) and os.path.isdir(save_path):
                shutil.rmtree(save_path)
            os.makedirs(save_path, exist_ok=True)
            template = 'batch_{}.h5'
            batch = 0
            for generator in [self.train_generator, self.test_generator]:
                for x_batch, y_batch in tqdm.tqdm(generator):
                    IPython.display.clear_output(wait=True)
                    features = self.feature_extractor.predict(x_batch)
                    file_path = os.path.join(save_path, template.format(batch))
                    with h5py.File(file_path, 'w') as file:
                        # encoded features and hard labels
                        file.create_dataset('features', data=features)
                        file.create_dataset('labels', data=y_batch)
                    batch += 1
                    if folder == 'train':
                        if batch >= self.step_size_train:
                            break
                    else:
                       if batch >= self.step_size_valid:
                            break

    def load_data(self, folder):
        '''yields (x_batch, y_batch) for model.fit()
        '''
        root_path = os.path.join(self.latent_path, folder)
        while True:
            for file_path in os.listdir(root_path):
                with h5py.File(os.path.join(root_path, file_path), 'r') as file:
                    yield (np.array(file['features']), np.array(file['labels']))

    def clear_session(self):
        tf.keras.backend.clear_session()

    def train(self,
              lr=None,
              optimizer=None,
              epochs=None,
              decay_lr=False,
              save_folder=None,
              notification = False):

        self.save_folder = save_folder

        # shape of VGG16 encoded features
        inputs = layers.Input(shape=self.latent_vectors)
        x = layers.Dense(self.num_classes, activation='softmax')(inputs)
        self.classifier = tf.keras.Model(inputs, x)

        self.classifier.compile(optimizer=optimizer(lr=lr),
                                loss='categorical_crossentropy',
                                metrics=['accuracy'])

        def lr_decay(epoch):
            alpha, decay = 1, 1
            return lr / (alpha + decay * epoch)
        callback_learning_rate = tf.keras.callbacks.LearningRateScheduler(lr_decay, verbose=True)
        plot_losses = PlotLosses()
        callback_is_nan = tf.keras.callbacks.TerminateOnNaN()
        callback_early = tf.keras.callbacks.EarlyStopping(monitor='loss', min_delta = .001, patience = 10)

        callbacks = [plot_losses, callback_is_nan, callback_early]
        callbacks += [callback_learning_rate] if decay_lr else []
        self.latent_train, self.latent_test = 'train', 'test'

        self.history = self.classifier.fit(
                  x = self.load_data(self.latent_train),
                  epochs=epochs,
                  workers=15,
                  steps_per_epoch=self.step_size_train,
                  validation_steps=self.step_size_valid,
                  validation_data=self.load_data(self.latent_test),
                  callbacks=callbacks)

        fig = self.plot_accuracy(self.history)
        if save_folder:
            asl_detection.save.save(save_folder, 'acc_loss', fig=fig)
            asl_detection.save.save(save_folder, 'model', self.classifier)
        if notification:
            self.notify(fig)
        self.images, self.labels = self.test_generator.next()

    def _visualize_feature_maps(self, image, _layers, scale):
        model_layers = self.feature_extractor.layers
        # Extracts the outputs
        layer_outputs = [layer.output for layer in self.feature_extractor.layers]
        # Creates a model that will return these outputs, given the model input
        activation_model = tf.keras.Model(inputs=self.feature_extractor.inputs, outputs=layer_outputs)
        # get activations
        activations = activation_model.predict(image)
        images_per_row = 4; count = -1
        # Displays the feature maps
        for layer, layer_activation in zip(model_layers, activations):
            if not isinstance(layer, layers.Conv2D):
                continue
            count += 1
            # show first 3 conv layers
            if count != _layers:
                continue
            n_features = layer_activation.shape[-1] # Number of features in the feature map
            size = layer_activation.shape[1] #The feature map has shape (1, size, size, n_features).
            n_cols = n_features // images_per_row # Tiles the activation channels in this matrix
            display_grid = np.zeros((size * n_cols, images_per_row * size))
            for col in range(n_cols): # Tiles each filter into a big horizontal grid
                for row in range(images_per_row):
                    channel_image = layer_activation[0, :, :, col * images_per_row + row]
                    # Post-processes the feature to make it visually palatable
                    channel_image -= channel_image.mean()
                    channel_image /= channel_image.std() + 1e-8
                    channel_image *= 64
                    channel_image += 128
                    channel_image = np.clip(channel_image, 0, 255).astype('uint8')
                    display_grid[col * size : (col + 1) * size, # Displays the grid
                                 row * size : (row + 1) * size] = channel_image
            fig_scale = scale / size
            fig = plt.figure(figsize=(fig_scale * display_grid.shape[1],
                                fig_scale * display_grid.shape[0]))
            plt.title(layer.name)
            plt.grid(False)
            plt.imshow(display_grid, aspect='auto', cmap='gray')
        if self.save_folder:
            asl_detection.save.save(self.save_folder, 'feature_maps', fig=fig)

    def visualize_feature_maps(self, index, _layers=1, scale=2):
        image = self.images[index:index+1]
        self._visualize_feature_maps(image, _layers, scale)

    def generate_heat_map(self, _input):
        self.grad_cam_names = [layer.name for layer in self.feature_extractor.layers if isinstance(layer, layers.Conv2D)]
        image = self.images[_input:_input+1] if isinstance(_input, int) else _input
        preds = self.classifier(self.feature_extractor(image))
        idx = np.argmax(preds[0])
        # initialize our gradient class activation map and build the heatmap
        cam = GradCAM(self.feature_extractor, idx, self.grad_cam_names[-1])
        heatmap = cam.compute_heatmap(image)
        (heatmap, overlay) = cam.overlay_heatmap(heatmap, image, self.img_size, alpha=0.4)
        label = self.category_map[idx]

        if isinstance(_input, int):
            description = 'image\ntrue: {} pred: {}\nconfidence: {:.3f}'.format\
            (self.category_map[np.argmax(self.labels[_input])], self.category_map[idx], preds[0][idx])
        else:
            description = 'pred: {}\nconfidence: {:.3f}'.format(self.category_map[idx], preds[0][idx])

        results = {'image': image, 'heatmap': heatmap, 'overlay': overlay, 'description': description, 'label': label}
        return results

    def visualize_heat_maps(self, index, rows=3, figsize=(8, 8)):
        f, axes = plt.subplots(rows, 3, figsize=figsize)
        for i in range(rows):
            results = self.generate_heat_map(index+i)

            axes[i, 0].imshow(results['image'].reshape(self.img_size, self.img_size, 3))
            axes[i, 1].imshow(results['heatmap'].reshape(self.img_size, self.img_size, 3))
            axes[i, 2].imshow(results['overlay'].reshape(self.img_size, self.img_size, 3))
            axes[i, 0].set_title(results['description']).set_size(12)
            axes[i, 1].set_title('heatmap')
            axes[i, 2].set_title('overlay')
            axes[i, 0].axis('off')
            axes[i, 1].axis('off')
            axes[i, 2].axis('off')
        plt.tight_layout(w_pad=0.1)
        if self.save_folder:
            asl_detection.save.save(self.save_folder, 'heat_maps', fig=f)

# Cell
class GradCAM:
    def __init__(self, model, classIdx, layerName=None):
        # store the model, the class index used to measure the class
        # activation map, and the layer to be used when visualizing
        # the class activation map
        self.model = model
        self.classIdx = classIdx
        self.layerName = layerName
        # if the layer name is None, attempt to automatically find
        # the target output layer
        if self.layerName is None:
            self.layerName = self.find_target_layer()
    def find_target_layer(self):
        # attempt to find the final convolutional layer in the network
        # by looping over the layers of the network in reverse order
        for layer in reversed(self.model.layers):
            # check to see if the layer has a 4D output
            if len(layer.output_shape) == 4:
                return layer.name
        # otherwise, we could not find a 4D layer so the GradCAM
        # algorithm cannot be applied
        raise ValueError("Could not find 4D layer. Cannot apply GradCAM.")
    def compute_heatmap(self, image, eps=1e-8):
        # construct our gradient model by supplying (1) the inputs
        # to our pre-trained model, (2) the output of the (presumably)
        # final 4D layer in the network, and (3) the output of the
        # softmax activations from the model
        gradModel = tf.keras.Model(
            inputs=[self.model.inputs[0]],
            outputs=[self.model.get_layer(self.layerName).output,
                self.model.output])
        # record operations for automatic differentiation
        with tf.GradientTape() as tape:
            # cast the image tensor to a float-32 data type, pass the
            # image through the gradient model, and grab the loss
            # associated with the specific class index
            inputs = tf.cast(image, tf.float32)
            (convOutputs, predictions) = gradModel(inputs)
            loss = predictions[:, self.classIdx]
        # use automatic differentiation to compute the gradients
        grads = tape.gradient(loss, convOutputs)
        # compute the guided gradients
        castConvOutputs = tf.cast(convOutputs > 0, "float32")
        castGrads = tf.cast(grads > 0, "float32")
        guidedGrads = castConvOutputs * castGrads * grads
        # the convolution and guided gradients have a batch dimension
        # (which we don't need) so let's grab the volume itself and
        # discard the batch
        convOutputs = convOutputs[0]
        # guidedGrads = guidedGrads[0]
        guidedGrads = grads[0]
        # compute the average of the gradient values, and using them
        # as weights, compute the ponderation of the filters with
        # respect to the weights
        weights = tf.reduce_mean(guidedGrads, axis=(0, 1))
        cam = tf.reduce_sum(tf.multiply(weights, convOutputs), axis=-1)
        # grab the spatial dimensions of the input image and resize
        # the output class activation map to match the input image
        # dimensions
        (w, h) = (image.shape[2], image.shape[1])
        heatmap = cv2.resize(cam.numpy(), (w, h))
        # normalize the heatmap such that all values lie in the range
        # [0, 1], scale the resulting values to the range [0, 255],
        # and then convert to an unsigned 8-bit integer
        numer = heatmap - np.min(heatmap)
        denom = (heatmap.max() - heatmap.min()) + eps
        heatmap = numer / denom
        heatmap = ((1 - heatmap) * 255).astype("uint8")
        # return the resulting heatmap to the calling function
        return heatmap
    def overlay_heatmap(self, heatmap, image, img_size, alpha=0.2, colormap=cv2.COLORMAP_JET):
        # apply the supplied color map to the heatmap and then
        # overlay the heatmap on the input image
        heatmap = cv2.applyColorMap(heatmap, colormap).reshape(1, img_size, img_size, 3)
        output = image*255*(1-alpha) + heatmap.reshape(1, img_size, img_size, 3)*alpha
        # return a 2-tuple of the color mapped heatmap and the output,
        # overlaid image
        output = np.uint8(output)
        return (heatmap, output)