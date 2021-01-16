# AUTOGENERATED! DO NOT EDIT! File to edit: 00_core.ipynb (unless otherwise specified).

__all__ = ['my_hello', 'draw_boxes']

# Cell
def my_hello(to):
    "prints hello"
    return f"hello {to}"

# Cell
def draw_boxes(hand_detector,
               img_paths,
               save_dir=None,
               classifier=None,
               show_classes=False,
               class_threshold=.6,
               nms_thresh=.6,
               figsize=(10, 10)):
    # define the expected input shape for the model
    input_w, input_h = 416, 416
    # define the anchors
    anchors = [[116,90, 156,198, 373,326], [30,61, 62,45, 59,119], [10,13, 16,30, 33,23]]

    for img_path in img_paths:
        # load and prepare image
        image, image_w, image_h = load_image_pixels(img_path, (input_w, input_h))

        yhat = hand_detector.predict(image)

        # define the probability threshold for detected objects
        boxes = list()
        for i in range(len(yhat)):
            # decode the output of the network
            boxes += decode_netout(yhat[i][0], anchors[i], class_threshold, input_h, input_w)
        # correct the sizes of the bounding boxes for the shape of the image
        correct_yolo_boxes(boxes, image_h, image_w, input_h, input_w)
        # suppress non-maximal boxes
        do_nms(boxes, nms_thresh)
        # define the labels
        labels = ['hand']
        # get the details of the detected objects
        v_boxes, v_labels, v_scores = get_boxes(boxes, labels, class_threshold)
        _draw_boxes(img_path,
                    v_boxes,
                    v_labels,
                    v_scores,
                    figsize,
                    save_dir,
                    classifier=classifier,
                    show_classes=show_classes)