"""Per-image pixel budget. This is a size guard, not a VRAM estimator."""


def require_pixel_limit(environment):
    limits = environment.get("limits") or {}
    maximum = limits.get("max_image_pixels") if isinstance(limits, dict) else None
    if maximum is None:
        raise ValueError(
            "尚未确定本机图像像素上限。请提醒用户确认，并在 "
            "config/environment.local.json 中设置 limits.max_image_pixels；本次不投递。"
        )
    if type(maximum) is not int or maximum <= 0:
        raise ValueError("limits.max_image_pixels 必须是已确认的正整数，不能用 0、布尔值或字符串代替。")
    return maximum


def check_image_pixels(environment, width, height, stage="sampling"):
    maximum = require_pixel_limit(environment)
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise ValueError(f"{stage}: 宽高必须是正整数")
    pixels = width * height
    if pixels > maximum:
        raise ValueError(
            f"{stage}: {width}x{height} = {pixels} 像素，超过已配置上限 {maximum}。"
            "请降低尺寸或在用户确认后调整本机配置；本次不投递。"
        )
    return {"stage": stage, "width": width, "height": height,
            "pixels": pixels, "max_image_pixels": maximum}
