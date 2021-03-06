import math
import os

os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import numpy as np
import tensorflow as tf
from matplotlib import pyplot as plt

from CityscapesHandler import CityscapesHandler
from PixelNet import PixelNet


def main():
    path_vgg16_vars = "./data/vgg_16.ckpt"  # downloadable at https://github.com/tensorflow/models/tree/master/research/slim
    model_save_path = "U:/PycharmProjects/models/run4/pixelnet"
    model_path = os.path.dirname('U:/PycharmProjects/models/checkpoint')
    continue_training = False

    n_train_images = 2975  # max: 2975
    # n_val_images = 25  # max: 500
    size_batch = 5
    n_batches = int(math.ceil(n_train_images / size_batch))  # if uneven the last few images are trained as well
    # n_validation_batches = int(math.ceil(n_val_images / size_batch))
    n_steps = 400
    pixel_sample_size = 10000 // size_batch  # per image
    lr = 1e-5/3
    input_image_shape = (224, 224)  # (width, height)
    # valid_after_n_steps = 1

    csh = CityscapesHandler()
    n_classes = csh.getNumTrainIDLabels()

    train_x, train_y = csh.getTrainSet(n_train_images, shape=input_image_shape)
    train_y = train_y[:, :, :, None]

    train_y[train_y == 255] = n_classes - 1
    train_y[train_y == -1] = n_classes - 1

    # val_x, val_y = csh.getValSet(n_val_images, shape=input_image_shape)
    # val_y = val_y[:, :, :, None]

    # val_y[val_y == 255] = n_classes - 1
    # val_y[val_y == -1] = n_classes - 1

    input_image_shape = train_x[0].shape

    graph = tf.Graph()
    with graph.as_default():
        train_images = tf.placeholder(tf.float32, shape=[None, input_image_shape[0], input_image_shape[1], 3],
                                      name='train_images')
        train_labels = tf.placeholder(tf.int32, shape=[None, input_image_shape[0], input_image_shape[1], 1],
                                      name='train_labels')

        # val_images = tf.placeholder(tf.float32, shape=[None, input_image_shape[0], input_image_shape[1], 3],
        #                             name='val_images')
        # val_labels = tf.placeholder(tf.int32, shape=[None, input_image_shape[0], input_image_shape[1], 1],
        #                             name='val_labels')

        index = tf.placeholder(tf.int32, shape=[None, 3], name='index')
        batch_size = tf.placeholder(tf.int64)

        train_dataset = tf.data.Dataset.from_tensor_slices((train_images, train_labels)).shuffle(
            buffer_size=n_batches).batch(batch_size).repeat()
        # val_dataset = tf.data.Dataset.from_tensor_slices((val_images, val_labels)).batch(batch_size).repeat()

        iterator = tf.data.Iterator.from_structure(train_dataset.output_types, train_dataset.output_shapes)

        batch_images, batch_labels = iterator.get_next()
        train_init_op = iterator.make_initializer(train_dataset)
        # val_init_op = iterator.make_initializer(val_dataset)

        pn = PixelNet()

        # preprocess
        train_bgr_norm = pn.preprocess_images(batch_images)

        logits, y = pn.build(images=train_bgr_norm, num_classes=n_classes, labels=batch_labels, index=index)
        y_one_hot = tf.one_hot(y, n_classes)
        # y = tf.reshape(y, [-1])
        logits = tf.reshape(logits, (-1, n_classes))
        y = tf.reshape(y_one_hot, (-1, n_classes))

        if not continue_training:
            vgg_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='vgg_16')[:-2]
            pixelnet_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)

        predictions = tf.argmax(logits, 1)

        with tf.name_scope('Loss'):
            # cross_entropy = tf.nn.softmax_cross_entropy_with_logits_v2(labels=y_one_hot, logits=logits)
            cross_entropy = tf.nn.softmax_cross_entropy_with_logits_v2(labels=y, logits=logits)
            loss_mean = tf.reduce_mean(cross_entropy)

        predicted_label = tf.argmax(logits, axis=-1)
        sparse_correct_label = tf.argmax(y, axis=-1)

        with tf.variable_scope("iou"):
            iou, iou_op = tf.metrics.mean_iou(sparse_correct_label, predicted_label, n_classes, name="iou_metric")
        # iou_metric_vars = tf.get_collection(tf.GraphKeys.LOCAL_VARIABLES, scope="iou_metric")

        # with tf.name_scope('iou'):
        #     # tf.Print(y, [y],)
        #     iou, conf_mat = tf.metrics.mean_iou(labels=y, predictions=predictions, num_classes=n_classes)
        #     # tf.Print(iou, [iou], "IoU values")
        #     # tf.Print(iou)

        optimizer = tf.train.AdamOptimizer(lr)
        train_op = optimizer.minimize(loss=cross_entropy, global_step=tf.train.get_global_step())

        if continue_training:
            pixelnet_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)

    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True

    with tf.Session(graph=graph, config=config) as sess:

        sess.run(tf.global_variables_initializer())
        sess.run(tf.local_variables_initializer())

        if continue_training:
            # load VGG model
            saver = tf.train.Saver(pixelnet_vars)
            ckpt = tf.train.get_checkpoint_state(model_path)
            saver.restore(sess, ckpt.model_checkpoint_path)

        else:
            saver = tf.train.Saver(vgg_vars)
            pixelnet_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)
            saver.restore(sess, path_vgg16_vars)

        # iou_metric_vars_initializer = tf.variables_initializer(var_list=iou_metric_vars)
        # sess.run(iou_metric_vars_initializer)

        # history container
        loss_history = np.zeros((n_steps,))
        iou_history = np.zeros((n_steps,))
        # loss_history_test = np.zeros((n_steps // valid_after_n_steps + 1 if valid_after_n_steps != 1 else n_steps,))
        # iou_history_test = np.zeros((n_steps // valid_after_n_steps + 1 if valid_after_n_steps != 1 else n_steps,))

        print("Training started")
        try:

            sess.run(train_init_op, feed_dict={train_images: train_x, train_labels: train_y, batch_size: size_batch})

            for step in range(n_steps):
                print("Epoch {}/{}".format(step + 1, n_steps))
                for batch_step in range(n_batches):
                    idx = pn.generate_sample_idxs(input_image_shape, size_batch, pixel_sample_size)
                    _, loss_value, iou_value = sess.run([train_op, loss_mean, iou_op], feed_dict={index: idx})
                    loss_history[step] += loss_value
                    print("--batch {}/{} - loss: {}".format(batch_step + 1, n_batches, loss_value))

                loss_history[step] /= n_batches
                iou_history[step] = sess.run(iou)

                print("Training Loss: {:.4f} -- IoU: {:.4f}".format(loss_history[step], iou_history[step]))

                try:
                    # save model checkpoint to disk
                    saver = tf.train.Saver(pixelnet_vars, save_relative_paths=False)
                    save_path = saver.save(sess,
                                           "{}_step_{}_loss_{}_iou_{}".format(model_save_path, step,
                                                                              str(loss_history[step])[:8].replace(
                                                                                  '.', '-'),
                                                                              str(iou_history[step])[:8].replace(
                                                                                  '.', '-')))
                    print("Model checkpoint saved in path: {}".format(save_path))
                except:
                    print("Model could not be saved.")

                # if step % valid_after_n_steps == 0:
                #     sess.run([val_init_op], feed_dict={val_images: val_x, val_labels: val_y, batch_size: n_val_images})
                #
                #     for _ in range(n_validation_batches):
                #         idx = pn.generate_sample_idxs(input_image_shape, size_batch, pixel_sample_size)
                #         loss_value, _ = sess.run([loss_mean, iou_op], feed_dict={index: idx})
                #         loss_history_test[step // valid_after_n_steps] += loss_value
                #
                #     loss_history_test[step // valid_after_n_steps] /= n_validation_batches
                #     iou_history_test[step // valid_after_n_steps] = sess.run(iou)
                    # print(
                    #     "Validation Loss: {:.4f} -- IoU: {:.4f}".format(loss_history_test[step // valid_after_n_steps],
                    #                                                     iou_history_test[step // valid_after_n_steps]))
                    # # loss_value = loss_value[0]

                    # sess.run(train_init_op,
                    #          feed_dict={train_images: train_x, train_labels: train_y, batch_size: size_batch})

        except KeyboardInterrupt:
            # interrupts training process after pressing ctrl+c
            pass

        print("Training done")

        try:
            # save new model to disk
            print("Saving model")
            saver = tf.train.Saver(pixelnet_vars, save_relative_paths=True)
            save_path = saver.save(sess,
                                   "{}_final_loss_{}_iou_{}".format(model_save_path, loss_history[-1], iou_history[-1]))
            print("Model saved in path: {}".format(save_path))
        except:
            print("Model could not be saved.")

        plt.figure(0)
        plt.plot(np.arange(1, n_steps + 1), loss_history, label="train")
        # plt.plot(np.arange(1, loss_history_test.shape[0] + 1), loss_history_test, label="test")
        plt.title("Loss Progress")
        plt.legend()
        plt.xlabel("Epoch")
        plt.ylabel("Loss")

        plt.savefig("Loss2.png")

        plt.figure(1)
        plt.plot(np.arange(1, n_steps + 1), iou_history, label="train")
        # plt.plot(np.arange(1, iou_history_test.shape[0] + 1), iou_history_test, label="test")
        plt.title("IoU Progress")
        plt.legend()
        plt.xlabel("Epoch")
        plt.ylabel("IoU")
        plt.savefig("IOU2.png")

        plt.show()


if __name__ == '__main__':
    main()
