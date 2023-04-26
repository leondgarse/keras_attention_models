from keras_cv_attention_models.beit.beit import Beit, keras_model_load_weights_from_pytorch_model


def DINOv2_ViT_Small14(input_shape=(518, 518, 3), num_classes=1000, activation="gelu", classifier_activation="softmax", pretrained="imagenet", **kwargs):
    patch_size = kwargs.pop("patch_size", 14)
    embed_dim = 384
    depth = 12
    num_heads = 6
    gamma_init_value = 1.0
    use_abs_pos_emb = True
    use_cat_head = True
    attn_qkv_bias = True
    force_reload_mismatch = patch_size != 14  # If patch_size not 14, force reload pos_emb and stem_conv weights
    return Beit(**locals(), model_name="dinov2_vit_small14", **kwargs)


def DINOv2_ViT_Base14(input_shape=(518, 518, 3), num_classes=1000, activation="gelu", classifier_activation="softmax", pretrained="imagenet", **kwargs):
    patch_size = kwargs.pop("patch_size", 14)
    embed_dim = 768
    depth = 12
    num_heads = 12
    gamma_init_value = 1.0
    use_abs_pos_emb = True
    use_cat_head = True
    attn_qkv_bias = True
    force_reload_mismatch = patch_size != 14  # If patch_size not 14, force reload pos_emb and stem_conv weights
    return Beit(**locals(), model_name="dinov2_vit_base14", **kwargs)


def DINOv2_ViT_Large14(input_shape=(518, 518, 3), num_classes=1000, activation="gelu", classifier_activation="softmax", pretrained="imagenet", **kwargs):
    patch_size = kwargs.pop("patch_size", 14)
    embed_dim = 1024
    depth = 24
    num_heads = 16
    gamma_init_value = 1.0
    use_abs_pos_emb = True
    use_cat_head = True
    attn_qkv_bias = True
    force_reload_mismatch = patch_size != 14  # If patch_size not 14, force reload pos_emb and stem_conv weights
    return Beit(**locals(), model_name="dinov2_vit_large14", **kwargs)


def DINOv2_ViT_Giant14(input_shape=(518, 518, 3), num_classes=1000, activation="gelu", classifier_activation="softmax", pretrained="imagenet", **kwargs):
    patch_size = kwargs.pop("patch_size", 14)
    embed_dim = 1536
    depth = 40
    num_heads = 24
    gamma_init_value = 1.0
    use_abs_pos_emb = True
    use_swish_gated_mlp = True
    mlp_ratio = 4096 / 1536
    use_cat_head = True
    attn_qkv_bias = True
    force_reload_mismatch = patch_size != 14  # If patch_size not 14, force reload pos_emb and stem_conv weights
    return Beit(**locals(), model_name="dinov2_vit_giant14", **kwargs)
