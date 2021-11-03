#!/usr/bin/env python3
import os
import tensorflow as tf
import tensorflow_addons as tfa
import keras_cv_attention_models
from tensorflow import keras
from keras_cv_attention_models.imagenet import data, callbacks


def train(compiled_model, epochs, train_dataset, test_dataset=None, initial_epoch=0, lr_scheduler=None, basic_save_name=None):
    if compiled_model.compiled_loss is None:
        print(">>>> Error: Model NOT compiled.")
        return None

    steps_per_epoch = len(train_dataset)
    if hasattr(lr_scheduler, "steps_per_epoch") and lr_scheduler.steps_per_epoch == -1:
        lr_scheduler.build(steps_per_epoch)
    is_lr_on_batch = True if hasattr(lr_scheduler, "steps_per_epoch") and lr_scheduler.steps_per_epoch > 0 else False

    if basic_save_name is None:
        basic_save_name = "{}".format(compiled_model.name)
    # ckpt_path = os.path.join("checkpoints", basic_save_name + "epoch_{epoch:03d}_val_acc_{val_acc:.4f}.h5")
    # cur_callbacks = [keras.callbacks.ModelCheckpoint(ckpt_path, monitor="val_loss", save_best_only=True)]
    # cur_callbacks = [keras.callbacks.ModelCheckpoint(os.path.join("checkpoints", basic_save_name + ".h5"))]
    cur_callbacks = [callbacks.MyCheckpoint(basic_save_name, monitor="val_acc")]
    hist_file = os.path.join("checkpoints", basic_save_name + "_hist.json")
    if initial_epoch == 0 and os.path.exists(hist_file):
        # os.remove(hist_file)
        os.rename(hist_file, hist_file + ".bak")
    cur_callbacks.append(callbacks.MyHistory(initial_file=hist_file))
    cur_callbacks.append(keras.callbacks.TerminateOnNaN())
    if lr_scheduler is not None:
        cur_callbacks.append(lr_scheduler)

    compiled_opt = compiled_model.optimizer
    compiled_opt = compiled_opt.inner_optimizer if isinstance(compiled_opt, keras.mixed_precision.LossScaleOptimizer) else compiled_opt
    if lr_scheduler is not None and isinstance(compiled_opt, tfa.optimizers.weight_decay_optimizers.DecoupledWeightDecayExtension):
        print(">>>> Append weight decay callback...")
        lr_base, wd_base = compiled_model.optimizer.lr.numpy(), compiled_model.optimizer.weight_decay.numpy()
        wd_callback = callbacks.OptimizerWeightDecay(lr_base, wd_base, is_lr_on_batch=is_lr_on_batch)
        cur_callbacks.append(wd_callback)  # should be after lr_scheduler

    compiled_model.fit(
        train_dataset,
        epochs=epochs,
        verbose=1,
        callbacks=cur_callbacks,
        initial_epoch=initial_epoch,
        steps_per_epoch=steps_per_epoch,
        validation_data=test_dataset,
        use_multiprocessing=True,
        workers=4,
    )


def parse_arguments(argv):
    import argparse

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-i", "--input_shape", type=int, default=160, help="Model input shape")
    parser.add_argument("-m", "--model", type=str, default="aotnet.AotNet50", help="Model name defined in this repo, format [sub_dir].[model_name]")
    parser.add_argument("-b", "--batch_size", type=int, default=256, help="Batch size")
    parser.add_argument("-e", "--epochs", type=int, default=105, help="Total epochs")
    parser.add_argument("-d", "--data_name", type=str, default="imagenet2012", help="Dataset name from tensorflow_datasets like imagenet2012 cifar10")
    parser.add_argument("-p", "--optimizer", type=str, default="LAMB", help="Optimizer name. One of [SGD, LAMB, AdamW].")
    parser.add_argument("-I", "--initial_epoch", type=int, default=0, help="Initial epoch when restore from previous interrupt")
    parser.add_argument("-s", "--basic_save_name", type=str, default=None, help="Basic save name for model and history. None means a combination of parameters")
    parser.add_argument("-r", "--restore_path", type=str, default=None, help="Restore model from saved h5 file. Higher priority than model")
    parser.add_argument("--pretrained", type=str, default=None, help="If build model with pretrained weights")
    parser.add_argument("--seed", type=int, default=None, help="Set random seed if not None")

    """ Loss arguments """
    loss_group = parser.add_argument_group("Loss arguments")
    loss_group.add_argument("--label_smoothing", type=float, default=0, help="Loss label smoothing value")

    """ Learning rate and weight decay arguments """
    lr_group = parser.add_argument_group("Learning rate and weight decay arguments")
    lr_group.add_argument("--lr_base_512", type=float, default=8e-3, help="Learning rate for batch_size=512")
    lr_group.add_argument(
        "--weight_decay",
        type=float,
        default=0.02,
        help="Weight decay. For SGD, it's L2 value. For AdamW, it will multiply with learning_rate. For LAMB, it's directly used",
    )
    lr_group.add_argument(
        "--lr_decay_steps",
        type=str,
        default="100",
        help="Learning rate decay steps. Single value like 100 for cosine decay. Set 30,60,90 for constant decay steps",
    )
    lr_group.add_argument("--lr_warmup", type=int, default=5, help="Learning rate warmup epochs")
    lr_group.add_argument("--lr_min", type=float, default=1e-6, help="Learning rate minimum value")

    """ Dataset parameters """
    ds_group = parser.add_argument_group("Dataset arguments")
    ds_group.add_argument("--magnitude", type=int, default=6, help="Randaug magnitude value")
    ds_group.add_argument("--mixup_alpha", type=float, default=0.1, help="Mixup alpha value")
    ds_group.add_argument("--cutmix_alpha", type=float, default=1.0, help="Cutmix alpha value")
    ds_group.add_argument("--random_crop_min", type=float, default=0.08, help="Random crop min value for RRC. Set 1 to disable RRC")
    ds_group.add_argument("--random_erasing_prob", type=float, default=0, help="Random erasing prob, can be used to replace cutout. Set 0 to disable")
    ds_group.add_argument("--rescale_mode", type=str, default="torch", help="Rescale mode, one of [tf, torch]")
    ds_group.add_argument("--central_crop", type=float, default=1.0, help="Central crop fraction. Set 1 to disable")
    ds_group.add_argument("--resize_method", type=str, default="bicubic", help="Resize method from tf.image.resize, like [bilinear, bicubic]")

    args = parser.parse_known_args(argv)[0]

    lr_decay_steps = args.lr_decay_steps.strip().split(",")
    if len(lr_decay_steps) > 1:
        # Constant decay steps
        args.lr_decay_steps = [int(ii.strip()) for ii in lr_decay_steps if len(ii.strip()) > 0]
    else:
        # Cosine decay
        args.lr_decay_steps = int(lr_decay_steps[0].strip())
    return args


if __name__ == "__main__":
    keras.mixed_precision.set_global_policy("mixed_float16")
    gpus = tf.config.experimental.get_visible_devices("GPU")
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)
    strategy = tf.distribute.MirroredStrategy() if len(gpus) > 1 else tf.distribute.OneDeviceStrategy(device="/gpu:0")

    # from keras_cv_attention_models import aotnet, coatnet, cmt
    import sys

    args = parse_arguments(sys.argv[1:])
    print(args)
    if args.seed is not None:
        print(">>>> Set random seed:", args.seed)
        tf.random.set_seed(args.seed)

    model = args.model.strip().split(".")
    input_shape = (args.input_shape, args.input_shape, 3)
    batch_size = args.batch_size * strategy.num_replicas_in_sync
    lr_base_512 = args.lr_base_512
    optimizer = args.optimizer.lower()
    weight_decay = args.weight_decay
    label_smoothing = args.label_smoothing
    lr_decay_steps = args.lr_decay_steps
    lr_warmup = args.lr_warmup
    lr_min = args.lr_min
    epochs = args.epochs
    initial_epoch = args.initial_epoch
    basic_save_name = args.basic_save_name
    restore_path = args.restore_path
    pretrained = args.pretrained

    train_dataset, test_dataset, total_images, num_classes, steps_per_epoch = data.init_dataset(
        data_name=args.data_name,
        input_shape=input_shape,
        batch_size=batch_size,
        mixup_alpha=args.mixup_alpha,
        cutmix_alpha=args.cutmix_alpha,
        rescale_mode=args.rescale_mode,
        central_crop=args.central_crop,
        random_crop_min=args.random_crop_min,
        resize_method=args.resize_method,
        random_erasing_prob=args.random_erasing_prob,
        magnitude=args.magnitude,
    )
    combined_name = "{}_batch_size_{}".format(args.data_name, batch_size)
    combined_name += "_randaug_{}_mixup_{}_cutmix_{}_RRC_{}".format(args.magnitude, args.mixup_alpha, args.cutmix_alpha, args.random_crop_min)

    lr_base = lr_base_512 * batch_size / 512
    if isinstance(lr_decay_steps, list):
        constant_lr_sch = lambda epoch: callbacks.constant_scheduler(epoch, lr_base=lr_base, lr_decay_steps=lr_decay_steps, warmup=lr_warmup)
        lr_scheduler = keras.callbacks.LearningRateScheduler(constant_lr_sch)
        epochs = epochs if epochs != 0 else lr_decay_steps[-1] + lr_decay_steps[0] + lr_warmup  # 124 for lr_decay_steps=[30, 60, 90], lr_warmup=4
    else:
        lr_scheduler = callbacks.CosineLrScheduler(
            lr_base, first_restart_step=lr_decay_steps, m_mul=0.5, t_mul=2.0, lr_min=lr_min, warmup=lr_warmup, steps_per_epoch=-1
        )
        # lr_scheduler = callbacks.CosineLrSchedulerEpoch(lr_base, first_restart_step=lr_decay_steps, m_mul=0.5, t_mul=2.0, lr_min=lr_min, warmup=lr_warmup)
        epochs = epochs if epochs != 0 else lr_decay_steps * 3 + lr_warmup  # 94 for lr_decay_steps=30, lr_warmup=4

    with strategy.scope():
        if restore_path:
            print(">>>> Restore model from:", restore_path)
            model = keras.models.load_model(restore_path)
        else:
            # model = cmt.CMTTiny(input_shape=input_shape, num_classes=num_classes, drop_connect_rate=0.2, drop_rate=0.2)
            # model = keras.applications.ResNet50(weights=None, input_shape=input_shape)
            # model = aotnet.AotNet50(num_classes=num_classes, input_shape=input_shape)
            if len(model) == 1:
                model = getattr(keras.applications, model[0])(classes=num_classes, weights=pretrained, input_shape=input_shape)
            else:
                model = getattr(getattr(keras_cv_attention_models, model[0]), model[1])(num_classes=num_classes, input_shape=input_shape, pretrained=pretrained)
            print(">>>> Built model name:", model.name)
        # sys.exit()

        if model.optimizer is None:
            if optimizer == "sgd":
                if weight_decay > 0:
                    from keras_cv_attention_models import model_surgery

                    model = model_surgery.add_l2_regularizer_2_model(model, weight_decay=weight_decay, apply_to_batch_normal=False)
                optimizer = keras.optimizers.SGD(learning_rate=lr_base, momentum=0.9)
            elif optimizer == "lamb":
                optimizer = tfa.optimizers.LAMB(learning_rate=lr_base, weight_decay_rate=weight_decay)
            elif optimizer == "adamw":
                optimizer = tfa.optimizers.AdamW(learning_rate=lr_base, weight_decay=lr_base * weight_decay)
            model.compile(optimizer=optimizer, loss=keras.losses.CategoricalCrossentropy(label_smoothing=label_smoothing), metrics=["acc"])

        compiled_opt = model.optimizer
        compiled_opt = compiled_opt.inner_optimizer if isinstance(compiled_opt, keras.mixed_precision.LossScaleOptimizer) else compiled_opt
        if basic_save_name is None and restore_path is not None:
            basic_save_name = os.path.splitext(os.path.basename(restore_path))[0]
            basic_save_name = basic_save_name[:-7] if basic_save_name.endswith("_latest") else basic_save_name
        elif basic_save_name is None:
            basic_save_name = "{}_{}_{}_lr{}_wd{}".format(model.name, combined_name, compiled_opt.__class__.__name__, lr_base_512, weight_decay)
        print(">>>> basic_save_name =", basic_save_name)
        # sys.exit()
        train(model, epochs, train_dataset, test_dataset, initial_epoch, lr_scheduler=lr_scheduler, basic_save_name=basic_save_name)
