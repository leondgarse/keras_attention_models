import os
import json
import numpy as np
from keras_cv_attention_models import backend
from keras_cv_attention_models.backend import callbacks


class CosineLrScheduler(callbacks.Callback):
    """
    >>> from keras_cv_attention_models.imagenet import callbacks
    >>> aa = callbacks.CosineLrScheduler(0.1, first_restart_step=5, steps_per_epoch=10, m_mul=0.5)
    >>> bb = [aa.on_train_batch_begin(ii) for ii in range(350)]
    >>> plt.plot(bb)
    >>> plt.grid(True)
    """

    def __init__(self, lr_base, first_restart_step, steps_per_epoch=-1, m_mul=0.5, t_mul=2.0, lr_min=1e-5, lr_warmup=-1, warmup_steps=0, cooldown_steps=0):
        super(CosineLrScheduler, self).__init__()
        self.lr_base, self.m_mul, self.t_mul, self.lr_min, self.steps_per_epoch = lr_base, m_mul, t_mul, lr_min, steps_per_epoch
        self.first_restart_step, self.warmup_steps, self.cooldown_steps, self.lr_warmup = first_restart_step, warmup_steps, cooldown_steps, lr_warmup
        self.init_step_num, self.cur_epoch, self.is_cooldown_epoch, self.previous_cooldown_steps, self.alpha = 0, 0, False, 0, lr_min / lr_base

        self.is_built = False
        if steps_per_epoch != -1:
            self.build(steps_per_epoch)

    def cosine_decay(self, step):
        factor = 0.5 * (1 + np.cos(np.pi * (np.minimum(step, self.first_restart_batch_step) / self.first_restart_batch_step)))
        return ((1 - self.alpha) * factor + self.alpha) * self.lr_base

    def cosine_decay_restarts(self, step):
        cur_stage = (self.restart_steps > step).argmax()
        cur_lr_base = self.lr_base * (self.m_mul**cur_stage)
        cur_total_decay_steps = self.first_restart_batch_step * (self.t_mul**cur_stage)
        cur_alpha = self.lr_min / cur_lr_base
        step -= 0 if cur_stage == 0 else self.restart_steps[cur_stage - 1]
        factor = 0.5 * (1 + np.cos(np.pi * (step / cur_total_decay_steps)))
        return ((1 - cur_alpha) * factor + cur_alpha) * cur_lr_base

    def build(self, steps_per_epoch=-1):
        # print(">>>> steps_per_epoch:", steps_per_epoch)
        if steps_per_epoch != -1:
            self.steps_per_epoch = steps_per_epoch

        self.first_restart_batch_step = self.first_restart_step * self.steps_per_epoch
        alpha = self.lr_min / self.lr_base
        if self.lr_min == self.lr_base * self.m_mul:  # Without restart
            self.schedule = self.cosine_decay
            self.cooldown_steps_start, self.cooldown_steps_end = np.array([]), np.array([])
        else:
            self.schedule = self.cosine_decay_restarts
            batch_steps_each_stage = [self.first_restart_batch_step * (self.t_mul**stage) for stage in range(5)]
            self.restart_steps = np.array([int(sum(batch_steps_each_stage[:stage])) for stage in range(1, 5)])
            self.cooldown_steps_start = np.array([int(self.restart_steps[stage] / self.steps_per_epoch + self.cooldown_steps * stage) for stage in range(4)])
            self.cooldown_steps_end = np.array([ii + self.cooldown_steps for ii in self.cooldown_steps_start])

        if self.warmup_steps != 0:
            self.warmup_batch_steps = self.warmup_steps * self.steps_per_epoch
            self.lr_warmup = self.lr_warmup if self.lr_warmup > 0 else self.lr_min
            self.warmup_lr_func = lambda ii: self.lr_warmup + (self.lr_base - self.lr_warmup) * ii / self.warmup_batch_steps
        else:
            self.warmup_batch_steps = 0
        self.is_built = True

    def get_lr_with_warmup_cooldown(self, global_iterNum):
        if global_iterNum < self.warmup_batch_steps:
            lr = self.warmup_lr_func(global_iterNum)
        elif self.is_cooldown_epoch:
            lr = self.lr_min  # cooldown
        else:
            # lr = self.schedule(global_iterNum - self.warmup_batch_steps - self.previous_cooldown_steps)
            lr = self.schedule(global_iterNum - self.previous_cooldown_steps)
        return lr

    def on_epoch_begin(self, cur_epoch, logs=None):
        if not self.is_built:
            self.build()

        self.init_step_num = int(self.steps_per_epoch * cur_epoch)
        self.cur_epoch = cur_epoch

        if self.cooldown_steps_end.shape[0] != 0:
            cooldown_end_pos = (self.cooldown_steps_end > cur_epoch).argmax()
            self.previous_cooldown_steps = self.cooldown_steps * cooldown_end_pos * self.steps_per_epoch
            if cur_epoch >= self.cooldown_steps_end[cooldown_end_pos] - self.cooldown_steps:
                self.is_cooldown_epoch = True
            else:
                self.is_cooldown_epoch = False
        lr = self.get_lr_with_warmup_cooldown(self.init_step_num)
        print("\nLearning rate for iter {} is {}, global_iterNum is {}".format(self.cur_epoch + 1, lr, self.init_step_num))

    def on_train_batch_begin(self, iterNum, logs=None):
        lr = self.get_lr_with_warmup_cooldown(iterNum + self.init_step_num)
        if self.model is not None:
            # self.set_value(self.model.optimizer.lr, lr)
            if hasattr(self.model.optimizer, "param_groups"):
                for param_group in self.model.optimizer.param_groups:
                    param_group["lr"] = lr
            else:
                self.model.optimizer.learning_rate = lr
        return lr


class CosineLrSchedulerEpoch(callbacks.Callback):
    """
    >>> from keras_cv_attention_models.imagenet import callbacks
    >>> aa = callbacks.CosineLrSchedulerEpoch(0.1, first_restart_step=50, m_mul=0.5)
    >>> bb = [aa.on_epoch_begin(ii) for ii in range(350)]
    >>> plt.plot(bb)
    >>> plt.grid(True)
    """

    def __init__(self, lr_base, first_restart_step, m_mul=0.5, t_mul=2.0, lr_min=1e-6, lr_warmup=-1, warmup_steps=0, cooldown_steps=0):
        super(CosineLrSchedulerEpoch, self).__init__()
        self.warmup_steps, self.cooldown_steps, self.lr_min, self.lr_base, self.alpha = warmup_steps, cooldown_steps, lr_min, lr_base, lr_min / lr_base
        self.first_restart_step, self.m_mul, self.t_mul = first_restart_step, m_mul, t_mul

        if lr_min == lr_base * m_mul:
            self.schedule = self.cosine_decay
            self.cooldown_steps_start, self.cooldown_steps_end = np.array([]), np.array([])
        else:
            self.schedule = self.cosine_decay_restarts
            epoch_steps_each_stage = [first_restart_step * (t_mul**stage) for stage in range(5)]
            self.restart_steps = np.array([int(sum(epoch_steps_each_stage[:stage])) for stage in range(1, 5)])
            self.cooldown_steps_start = np.array([int(self.restart_steps[stage] + cooldown_steps * stage) for stage in range(4)])
            self.cooldown_steps_end = np.array([ii + cooldown_steps for ii in self.cooldown_steps_start])

        if warmup_steps != 0:
            self.lr_warmup = lr_warmup if lr_warmup > 0 else lr_min
            self.warmup_lr_func = lambda ii: self.lr_warmup + (lr_base - self.lr_warmup) * ii / warmup_steps

    def cosine_decay(self, step):
        factor = 0.5 * (1 + np.cos(np.pi * (np.minimum(step, self.first_restart_step) / self.first_restart_step)))
        return ((1 - self.alpha) * factor + self.alpha) * self.lr_base

    def cosine_decay_restarts(self, step):
        cur_stage = (self.restart_steps > step).argmax()
        cur_lr_base = self.lr_base * (self.m_mul**cur_stage)
        cur_total_decay_steps = self.first_restart_step * (self.t_mul**cur_stage)
        cur_alpha = self.lr_min / cur_lr_base
        step -= 0 if cur_stage == 0 else self.restart_steps[cur_stage - 1]
        factor = 0.5 * (1 + np.cos(np.pi * (step / cur_total_decay_steps)))
        return ((1 - cur_alpha) * factor + cur_alpha) * cur_lr_base

    def on_epoch_begin(self, epoch, logs=None):
        if epoch < self.warmup_steps:
            lr = self.warmup_lr_func(epoch)
        elif self.cooldown_steps_end.shape[0] != 0:
            cooldown_end_pos = (self.cooldown_steps_end > epoch).argmax()
            if epoch >= self.cooldown_steps_end[cooldown_end_pos] - self.cooldown_steps:
                lr = self.lr_min  # cooldown
            else:
                # lr = self.schedule(epoch - self.warmup_steps)
                lr = self.schedule(epoch - self.cooldown_steps * cooldown_end_pos)
        else:
            lr = self.schedule(epoch)

        if self.model is not None:
            # self.set_value(self.model.optimizer.lr, lr)
            if hasattr(self.model.optimizer, "param_groups"):
                for param_group in self.model.optimizer.param_groups:
                    param_group["lr"] = lr
            else:
                self.model.optimizer.learning_rate = lr
        print("\nLearning rate for iter {} is {}".format(epoch + 1, lr))
        return lr


class LearningRateScheduler(callbacks.Callback):
    def __init__(self, schedule, verbose=0):
        super().__init__()
        self.schedule, self.verbose = schedule, verbose

    def on_epoch_begin(self, epoch, logs=None):
        lr = self.schedule(epoch)
        if self.model is not None:
            if hasattr(self.model.optimizer, "param_groups"):
                for param_group in self.model.optimizer.param_groups:
                    param_group["lr"] = lr
            else:
                self.model.optimizer.learning_rate = lr
        print("\nLearning rate for iter {} is {}".format(epoch + 1, lr))
        return lr

    def on_epoch_end(self, epoch, logs=None):
        logs = logs or {}
        if hasattr(self.model, "optimizer") and hasattr(self.model.optimizer, "lr"):
            lr = self.model.optimizer.lr
        elif hasattr(self.model, "optimizer") and hasattr(self.model.optimizer, "param_groups"):
            lr = self.model.optimizer.param_groups[-1]["lr"]
        lr = lr.value() if hasattr(lr, "value") else lr
        lr = lr.item() if hasattr(lr, "item") else lr
        logs["lr"] = lr


def constant_scheduler(epoch, lr_base, lr_decay_steps, decay_rate=0.1, warmup_steps=0):
    if epoch < warmup_steps:
        lr = lr_base * (epoch + 1) / (warmup_steps + 1)
    else:
        # epoch -= warmup_steps
        lr = lr_base * decay_rate ** np.sum(epoch >= np.array(lr_decay_steps))
    print("\nLearning rate for iter {} is {}".format(epoch + 1, lr))
    return lr


def exp_scheduler(epoch, lr_base=0.1, decay_step=1, decay_rate=0.9, lr_min=0, warmup_steps=0):
    if epoch < warmup_steps:
        lr = (lr_base - lr_min) * (epoch + 1) / (warmup_steps + 1)
    else:
        # epoch -= warmup_steps
        lr = lr_base * decay_rate ** (epoch / decay_step)
        lr = lr if lr > lr_min else lr_min
    # print("Learning rate for iter {} is {}".format(epoch + 1, lr))
    return lr


class OptimizerWeightDecay(callbacks.Callback):
    def __init__(self, lr_base, wd_base, is_lr_on_batch=False):
        from tensorflow.keras import backend as K

        super(OptimizerWeightDecay, self).__init__()
        self.wd_m = wd_base / lr_base
        self.lr_base, self.wd_base = lr_base, wd_base
        # self.model.optimizer.weight_decay = lambda: wd_m * self.model.optimizer.lr
        self.is_lr_on_batch = is_lr_on_batch
        if is_lr_on_batch:
            self.on_train_batch_begin = self.__update_wd__
        else:
            self.on_epoch_begin = self.__update_wd__

        self.get_value, self.set_value = K.get_value, K.set_value

    def __update_wd__(self, step, log=None):
        if self.model is not None:
            wd = self.wd_m * self.get_value(self.model.optimizer.lr)
            # wd = self.wd_base * K.get_value(self.model.optimizer.lr)
            self.set_value(self.model.optimizer.weight_decay, wd)
        # wd = self.model.optimizer.weight_decay
        if not self.is_lr_on_batch or step == 0:
            print("Weight decay is {}".format(wd))


class MyHistory(callbacks.Callback):
    def __init__(self, initial_file=None):
        super(MyHistory, self).__init__()
        if initial_file and os.path.exists(initial_file):
            with open(initial_file, "r") as ff:
                self.history = json.load(ff)
        else:
            self.history = {}
        self.initial_file = initial_file

    def on_epoch_end(self, epoch, logs=None):
        logs = logs or {}
        lr = logs.pop("lr", float("nan"))
        if hasattr(self.model, "optimizer") and hasattr(self.model.optimizer, "lr"):
            lr = self.model.optimizer.lr
        elif hasattr(self.model, "optimizer") and hasattr(self.model.optimizer, "param_groups"):
            lr = self.model.optimizer.param_groups[-1]["lr"]
        lr = lr.value() if hasattr(lr, "value") else lr
        lr = lr.item() if hasattr(lr, "item") else lr
        self.history.setdefault("lr", []).append(float(lr))

        for k, v in logs.items():
            k = "accuracy" if "accuracy" in k else k
            self.history.setdefault(k, []).append(float(v))

        if hasattr(self.model, "losses") and len(self.model.losses) != 0:  # Has regular_loss
            # regular_loss = functional.reduce_sum(self.model.losses).numpy()
            regular_loss = np.sum(self.model.losses)
            self.history.setdefault("regular_loss", []).append(float(regular_loss))
            self.history["loss"][-1] -= regular_loss
            if "val_loss" in self.history:
                self.history["val_loss"][-1] -= regular_loss

        model_history = self.model.history.history if hasattr(self.model.history, "history") else self.model.history
        if "val_ap_ar" in model_history:  # save coco val_ap_ar
            self.history.setdefault("val_ap_ar", []).append(model_history["val_ap_ar"][-1])

        if self.initial_file:
            with open(self.initial_file, "w") as ff:
                json.dump(self.history, ff)

    def print_hist(self):
        print("{")
        for kk, vv in self.history.items():
            print("  '%s': %s," % (kk, vv))
        print("}")


class MyCheckpoint(callbacks.Callback):
    """Save latest and best one"""

    def __init__(self, basic_save_name, monitor="val_acc", mode="auto", save_path="checkpoints"):
        super(MyCheckpoint, self).__init__()
        self.suffix = ".pt" if backend.is_torch_backend else ".h5"  # not saving .keras currently, reading weights from it is slower..
        # if backend.is_torch_backend:
        #     self.suffix = ".pt"
        # else:
        #     try:
        #         is_tf2_13 = int(tf.__version__.split(".")[0]) >= 2 and int(tf.__version__.split(".")[1]) >= 13
        #     except:
        #         is_tf2_13 = False
        #     self.suffix = ".keras" if is_tf2_13 else ".h5"
        self.basic_save_name, self.mode, self.save_path = basic_save_name, mode, save_path
        self.__init_monitor_strategy__(monitor)

    def __init_monitor_strategy__(self, monitor):
        import re

        self.monitor = monitor
        monitor_save_name = self.basic_save_name + "_epoch_{}_" + monitor + "_{}" + self.suffix
        self.monitor_save_re = re.compile(monitor_save_name.format("\d*", "[\d\.]*"))
        self.monitor_save = os.path.join(self.save_path, monitor_save_name)
        self.latest_save = os.path.join(self.save_path, self.basic_save_name + "_latest" + self.suffix)
        self.is_better = (lambda cur, pre: cur <= pre) if self.mode == "min" or "loss" in monitor else (lambda cur, pre: cur >= pre)
        self.pre_best = 1e5 if self.mode == "min" or "loss" in monitor else -1e5

    def on_epoch_end(self, epoch, logs={}):
        # tf.print(">>>> Save latest to:", self.latest_save)
        # print(">>>> logs:", logs)
        if self.model is not None:
            print("\n>>>> Save latest to:", self.latest_save)
            self.model.save(self.latest_save)
        if self.monitor is not None and self.monitor not in logs:
            all_val_acc = [ii for ii in logs.keys() if "val" in ii and "acc" in ii]
            all_val_loss = [ii for ii in logs.keys() if "val" in ii and "loss" in ii]
            if len(all_val_acc) > 0:
                self.__init_monitor_strategy__(all_val_acc[0])
            elif len(all_val_loss) > 0:
                self.__init_monitor_strategy__(all_val_loss[0])
            else:
                # self.__init_monitor_strategy__("loss")
                self.monitor = None  # Not saving if not using eval dataset

        cur_monitor_val = logs.get(self.monitor, self.pre_best)
        if self.monitor is not None and self.is_better(cur_monitor_val, self.pre_best):
            self.pre_best = cur_monitor_val
            # pre_monitor_saves = tf.io.gfile.glob(self.monitor_save_re)
            pre_monitor_saves = [ii for ii in os.listdir(self.save_path) if self.monitor_save_re.match(ii)]
            # tf.print(">>>> pre_monitor_saves:", pre_monitor_saves)
            if len(pre_monitor_saves) != 0:
                os.remove(os.path.join(self.save_path, pre_monitor_saves[0]))
            monitor_save = self.monitor_save.format(epoch + 1, "{:.4f}".format(cur_monitor_val))
            print(">>>> Save best to:", monitor_save)
            if self.model is not None:
                self.model.save(monitor_save)


""" Currently for Torch Only """


class ModelEMA(callbacks.Callback):
    """Updated Exponential Moving Average (EMA) from https://github.com/rwightman/pytorch-image-models
    Keeps a moving average of everything in the model state_dict (parameters and buffers)
    For EMA details see https://www.tensorflow.org/api_docs/python/tf/train/ExponentialMovingAverage
    To disable EMA set the `enabled` attribute to `False`.
    """

    def __init__(self, basic_save_name=None, save_path="checkpoints", decay=0.9999, tau=2000, updates=0):
        self.basic_save_name, self.save_path, self.decay, self.tau, self.updates = basic_save_name, save_path, decay, tau, updates
        super().__init__()

    def set_model(self, model):
        from copy import deepcopy

        self.model = model
        self.ema = deepcopy(model).eval()  # FP32 EMA
        for p in self.ema.parameters():
            p.requires_grad_(False)
        self.basic_save_name = model.name if self.basic_save_name is None else self.basic_save_name
        self.save_file_path = os.path.join(save_path, basic_save_name) + "_ema.h5"
        self.enabled = True

    def on_train_batch_end(self, batch, logs=None):
        if not self.enabled:
            return
        self.updates += 1
        cur_decay = self.decay * (1 - np.exp(-self.updates / self.tau))  # decay exponential ramp (to help early epochs)
        model_state_dict = self.model.state_dict()  # model state_dict
        for name, param in self.ema.state_dict().items():
            if param.dtype.is_floating_point:  # true for FP16 and FP32
                param *= cur_decay  # Ensential in this way, in place operation
                param += (1 - cur_decay) * model_state_dict[name].detach()  # Update EMA parameters

    def on_epoch_end(self, cur_epoch, logs=None):
        print(">>>> Save EMA model to:", self.save_file_path)
        self.ema.save(self.save_file_path)


class CloseMosaic(callbacks.Callback):
    def __init__(self, dataset, close_mosaic_epoch=90):
        self.dataset, self.close_mosaic_epoch = dataset, close_mosaic_epoch
        super().__init__()

    def on_epoch_begin(self, cur_epoch, logs=None):
        if cur_epoch == self.close_mosaic_epoch:
            print(">>>> Closing dataset mosaic")
            if hasattr(self.dataset, "mosaic"):
                self.dataset.mosaic = 0
            elif hasattr(self.dataset, "dataset") and hasattr(self.dataset.dataset, "mosaic"):  # Torch dataloader
                self.dataset.dataset.mosaic = 0


class WarmupTrain(callbacks.Callback):
    """
    import kecam
    model = kecam.yolov8.YOLOV8_N(pretrained=None)
    optimizer = build_optimizer(model)
    model.train_compile(optimizer=optimizer, grad_accumulate=4)
    warmup_train = WarmupTrain(steps_per_epoch=100, warmup_epochs=3)
    warmup_train.set_model(model)

    accumulates, momentums, lrs = [], [], [[] for _ in model.optimizer.param_groups]
    for epoch in range(warmup_train.warmup_epochs + 3):
        warmup_train.on_epoch_begin(epoch)
        for batch in range(warmup_train.steps_per_epoch):
            warmup_train.on_train_batch_begin(batch)
            accumulates.append(model.grad_accumulate)
            momentums.append(model.optimizer.param_groups[0]["momentum"])
            for id, group in enumerate(model.optimizer.param_groups):
                lrs[id].append(group['lr'])

    fig, axes = plt.subplots(1, 5, figsize=[20, 4])
    names = ["grad_accumulate", "momentum", "group 0 lr", "group 1 lr", "group 2 lr"]
    for id, (name, values) in enumerate(zip(names, [accumulates, momentums, *lrs])):
        axes[id].plot(values)
        axes[id].set_title(name)
        axes[id].grid(True)
    fig.tight_layout()
    """

    def __init__(self, steps_per_epoch, warmup_epochs=3, warmup_momentum=0.8, warmup_bias_lr=0.1):
        self.steps_per_epoch, self.warmup_epochs, self.warmup_momentum, self.warmup_bias_lr = steps_per_epoch, warmup_epochs, warmup_momentum, warmup_bias_lr
        self.warmup_batch_steps = steps_per_epoch * warmup_epochs
        self.cur_epoch = 0
        super().__init__()

    def set_model(self, model):
        super().set_model(model)
        self.target_momentums = [group.get("momentum", 0) for group in self.model.optimizer.param_groups]
        self.target_lrs = [group.get("lr", 0) for group in self.model.optimizer.param_groups]
        self.target_grad_accumulate = getattr(self.model, "grad_accumulate", 0)

    def on_epoch_begin(self, cur_epoch, logs=None):
        self.cur_epoch = cur_epoch
        self.init_step_num = int(self.steps_per_epoch * cur_epoch)

    def on_train_batch_begin(self, batch, logs=None):
        if self.cur_epoch >= self.warmup_epochs:
            return

        warmup_ratio = (self.init_step_num + batch) / self.warmup_batch_steps
        if self.target_grad_accumulate > 1:
            self.model.grad_accumulate = round(warmup_ratio * self.target_grad_accumulate)

        for group_num, group in enumerate(self.model.optimizer.param_groups):
            warmup_lr = self.warmup_bias_lr if group_num == 0 else 0
            group["lr"] = warmup_lr + warmup_ratio * (self.target_lrs[group_num] - warmup_lr)
            if "momentum" in group:
                group["momentum"] = self.warmup_momentum + warmup_ratio * (self.target_momentums[group_num] - self.warmup_momentum)
