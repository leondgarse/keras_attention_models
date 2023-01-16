import tensorflow as tf
from tensorflow import keras
from keras_cv_attention_models.attention_layers import (
    activation_by_name,
    add_with_layer_scale_and_drop_block,
    conv2d_no_bias,
    layer_norm,
    mlp_block,
    mlp_block_with_depthwise_conv,
    multi_head_self_attention,
    output_block,
    add_pre_post_process,
)
from keras_cv_attention_models.download_and_load import reload_model_weights

LAYER_NORM_EPSILON = 1e-6

PRETRAINED_DICT = {
    "caformer_small18": {"imagenet": {224: "b8a824d4197161286de2aef08c1be379", 384: ""}},
}


def meta_former_block(inputs, use_attn=False, head_dim=32, mlp_ratio=4, layer_scale=0, residual_scale=0, drop_rate=0, activation="star_relu", name=""):
    input_channel = inputs.shape[-1]

    """ attention """
    nn = layer_norm(inputs, epsilon=LAYER_NORM_EPSILON, center=False, name=name + "attn_")
    # nn = conv_pool_attention_mixer(nn, num_heads, num_attn_low_heads=num_attn_low_heads, pool_size=pool_size, activation=activation, name=name + "attn_")
    if use_attn:
        nn = multi_head_self_attention(nn, num_heads=input_channel // head_dim, name=name + "mhsa_")
    else:
        nn = mlp_block_with_depthwise_conv(nn, input_channel * 2, kernel_size=7, use_bias=False, activation=(activation, None), name=name + "mlp_sep_")
    attn_out = add_with_layer_scale_and_drop_block(inputs, nn, layer_scale=layer_scale, residual_scale=residual_scale, drop_rate=drop_rate, name=name + "attn_")

    """ MLP """
    nn = layer_norm(attn_out, epsilon=LAYER_NORM_EPSILON, center=False, name=name + "mlp_")
    nn = mlp_block(nn, input_channel * mlp_ratio, use_bias=False, activation=activation, name=name + "mlp_")
    nn = add_with_layer_scale_and_drop_block(attn_out, nn, layer_scale=layer_scale, residual_scale=residual_scale, drop_rate=drop_rate, name=name + "mlp_")
    return nn


def CAFormer(
    num_blocks=[3, 3, 9, 3],
    out_channels=[64, 128, 320, 512],
    block_types=["conv", "conv", "transform", "transform"],
    head_dim=32,
    mlp_ratios=4,
    head_filter=2048,
    head_filter_activation="squared_relu",
    input_shape=(224, 224, 3),
    num_classes=1000,
    activation="star_relu",
    drop_connect_rate=0,
    dropout=0,
    layer_scales=0,
    residual_scales=[0, 0, 1, 1],
    classifier_activation="softmax",
    pretrained=None,
    model_name="caformer",
    kwargs=None,
):
    inputs = keras.layers.Input(input_shape)

    """ Stem """
    nn = keras.layers.ZeroPadding2D(padding=2, name="stem_")(inputs)  # padding=2
    nn = conv2d_no_bias(nn, out_channels[0], kernel_size=7, strides=4, padding="valid", use_bias=True, name="stem_")
    nn = layer_norm(nn, epsilon=LAYER_NORM_EPSILON, center=False, name="stem_")

    """ stacks """
    total_blocks = sum(num_blocks)
    global_block_id = 0
    for stack_id, (num_block, out_channel, block_type) in enumerate(zip(num_blocks, out_channels, block_types)):
        use_attn = True if block_type[0].lower() == "t" else False

        stack_name = "stack{}_".format(stack_id + 1)
        if stack_id > 0:
            nn = layer_norm(nn, epsilon=LAYER_NORM_EPSILON, center=False, name=stack_name + "downsample_")
            nn = conv2d_no_bias(nn, out_channel, 3, strides=2, padding="same", use_bias=True, name=stack_name + "downsample_")

        mlp_ratio = mlp_ratios[stack_id] if isinstance(mlp_ratios, (list, tuple)) else mlp_ratios
        layer_scale = layer_scales[stack_id] if isinstance(layer_scales, (list, tuple)) else layer_scales
        residual_scale = residual_scales[stack_id] if isinstance(residual_scales, (list, tuple)) else residual_scales
        for block_id in range(num_block):
            name = stack_name + "block{}_".format(block_id + 1)
            block_drop_rate = drop_connect_rate * global_block_id / total_blocks
            nn = meta_former_block(nn, use_attn, head_dim, mlp_ratio, layer_scale, residual_scale, block_drop_rate, activation=activation, name=name)
            global_block_id += 1

    if num_classes > 0:
        nn = keras.layers.GlobalAveragePooling2D(name="avg_pool")(nn)
        nn = layer_norm(nn, epsilon=LAYER_NORM_EPSILON, name="pre_output_")
        if head_filter > 0:
            nn = keras.layers.Dense(head_filter, use_bias=True, name="feature_dense")(nn)
            head_filter_activation = head_filter_activation if head_filter_activation is not None else activation
            nn = activation_by_name(nn, activation=head_filter_activation, name="feature_")
            nn = layer_norm(nn, name="feature_")  # epsilon=1e-5
        if dropout > 0:
            nn = keras.layers.Dropout(dropout, name="head_drop")(nn)
        nn = keras.layers.Dense(num_classes, dtype="float32", activation=classifier_activation, name="predictions")(nn)

    model = tf.keras.models.Model(inputs, nn, name=model_name)
    add_pre_post_process(model, rescale_mode="torch")
    reload_model_weights(model, PRETRAINED_DICT, "caformer", pretrained)
    return model


def CAFormerSmall18(input_shape=(224, 224, 3), num_classes=1000, activation="star_relu", classifier_activation="softmax", pretrained="imagenet", **kwargs):
    return CAFormer(**locals(), model_name="caformer_small18", **kwargs)


def CAFormerSmall36(input_shape=(224, 224, 3), num_classes=1000, activation="star_relu", classifier_activation="softmax", pretrained="imagenet", **kwargs):
    num_blocks = [3, 12, 18, 3]
    return CAFormer(**locals(), model_name="caformer_small36", **kwargs)


def CAFormerMedium36(input_shape=(224, 224, 3), num_classes=1000, activation="star_relu", classifier_activation="softmax", pretrained="imagenet", **kwargs):
    num_blocks = [3, 12, 18, 3]
    out_channels = [96, 192, 384, 576]
    head_filter = out_channels[-1] * 4
    return CAFormer(**locals(), model_name="caformer_medium36", **kwargs)


def CAFormerBig36(input_shape=(224, 224, 3), num_classes=1000, activation="star_relu", classifier_activation="softmax", pretrained="imagenet", **kwargs):
    num_blocks = [3, 12, 18, 3]
    out_channels = [128, 256, 512, 768]
    head_filter = out_channels[-1] * 4
    return CAFormer(**locals(), model_name="caformer_big36", **kwargs)
