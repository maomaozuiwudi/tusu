# ImageBatch 图速 — 图片处理操作（纯函数，PIL进PIL出）
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
import io
import numpy as np
import cv2


def compress_image(img, quality=85, target_fmt="保持原格式"):
    fmt_map = {"JPEG": "JPEG", "PNG": "PNG", "WebP": "WEBP", "保持原格式": None}
    fmt = fmt_map.get(target_fmt)
    if fmt is None:
        fmt = img.format or "JPEG"

    if img.mode == "RGBA" and fmt in ("JPEG", "JPEG"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    save_kw = {"format": fmt, "quality": quality}
    if fmt in ("JPEG", "WEBP"):
        save_kw["optimize"] = True
    img.save(buf, **save_kw)
    buf.seek(0)
    return Image.open(buf)


def resize_image(img, width, height, mode="crop"):
    ow, oh = img.size
    tw, th = width, height

    if mode == "stretch":
        return img.resize((tw, th), Image.LANCZOS)

    if mode == "fit":
        ratio = min(tw / ow, th / oh)
        nw, nh = int(ow * ratio), int(oh * ratio)
        resized = img.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA" if img.mode == "RGBA" else "RGB", (tw, th), (255, 255, 255, 255) if img.mode != "RGBA" else (0, 0, 0, 0))
        canvas.paste(resized, ((tw - nw) // 2, (th - nh) // 2))
        return canvas

    # 默认 crop — 中心裁剪，不拉伸
    ratio = max(tw / ow, th / oh)
    nw, nh = int(ow * ratio), int(oh * ratio)
    resized = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def add_text_watermark(img, text, position="右下角", font_size=36, opacity=128):
    img = img.convert("RGBA")
    w, h = img.size

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("msyh.ttc", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("simhei.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    margin = 20

    pos_map = {
        "右下角": (w - tw - margin, h - th - margin),
        "左下角": (margin, h - th - margin),
        "左上角": (margin, margin),
        "右上角": (w - tw - margin, margin),
        "居中": ((w - tw) // 2, (h - th) // 2),
    }

    if position == "平铺":
        spacing_x = tw + 100
        spacing_y = th + 100
        for y in range(0, h, spacing_y):
            for x in range(0, w, spacing_x):
                draw.text((x, y), text, fill=(255, 255, 255, opacity), font=font)
    else:
        x, y = pos_map.get(position, (w - tw - margin, h - th - margin))
        draw.text((x, y), text, fill=(255, 255, 255, opacity), font=font)

    result = Image.alpha_composite(img, overlay)
    return result.convert("RGB")


def add_image_watermark(img, wm_img, position="右下角", scale=0.15):
    img = img.convert("RGBA")
    wm = wm_img.convert("RGBA")

    wm_w = int(img.width * scale)
    wm_h = int(wm.height * (wm_w / wm.width))
    wm = wm.resize((wm_w, wm_h), Image.LANCZOS)

    margin = 20
    pos_map = {
        "右下角": (img.width - wm.width - margin, img.height - wm.height - margin),
        "左下角": (margin, img.height - wm.height - margin),
        "左上角": (margin, margin),
        "右上角": (img.width - wm.width - margin, margin),
        "居中": ((img.width - wm.width) // 2, (img.height - wm.height) // 2),
    }
    x, y = pos_map.get(position, (img.width - wm.width - margin, img.height - wm.height - margin))

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay.paste(wm, (x, y), mask=wm)
    result = Image.alpha_composite(img, overlay)
    return result.convert("RGB")


def convert_format(img, target_fmt="JPEG", quality=85):
    fmt = target_fmt.upper()

    if fmt == "HEIC":
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            pass

    if fmt in ("JPEG", "JPG"):
        if img.mode == "RGBA":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
    elif fmt == "PNG":
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
    elif fmt == "WEBP":
        buf = io.BytesIO()
        save_kw = {"format": "WEBP", "quality": quality}
        if img.mode == "RGBA":
            save_kw["lossless"] = False
        img.save(buf, **save_kw)
    elif fmt == "BMP":
        buf = io.BytesIO()
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(buf, format="BMP")
    elif fmt == "HEIC":
        buf = io.BytesIO()
        img.save(buf, format="HEIF", quality=quality)
    else:
        return img

    buf.seek(0)
    return Image.open(buf)


def change_dpi(img, dpi=300):
    buf = io.BytesIO()
    fmt = img.format or "JPEG"
    save_kw = {"format": fmt, "dpi": (dpi, dpi)}
    if img.mode == "RGBA":
        img = img.convert("RGB")
    if fmt == "JPEG":
        save_kw["quality"] = 95
        save_kw["optimize"] = True
    img.save(buf, **save_kw)
    buf.seek(0)
    return Image.open(buf)


def add_border_effect(img, border_px=20, color="#FFFFFF", corner_radius=0, shadow_blur=0):
    img = img.convert("RGBA")
    iw, ih = img.size

    try:
        color_rgb = tuple(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        color_rgb = (255, 255, 255)

    pad = border_px + shadow_blur
    canvas_w = iw + pad * 2
    canvas_h = ih + pad * 2
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # 阴影
    if shadow_blur > 0:
        shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_rect = [
            pad - shadow_blur // 2,
            pad - shadow_blur // 2,
            pad + iw + shadow_blur // 2,
            pad + ih + shadow_blur // 2,
        ]
        if corner_radius > 0:
            shadow_draw.rounded_rectangle(shadow_rect, corner_radius + shadow_blur // 2,
                                          fill=(0, 0, 0, 80))
        else:
            shadow_draw.rectangle(shadow_rect, fill=(0, 0, 0, 80))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(shadow_blur))
        canvas = Image.alpha_composite(canvas, shadow_layer)

    # 背景色
    draw = ImageDraw.Draw(canvas)
    bg_rect = [pad, pad, pad + iw, pad + ih]
    if corner_radius > 0:
        draw.rounded_rectangle(bg_rect, corner_radius, fill=color_rgb)
    else:
        draw.rectangle(bg_rect, fill=color_rgb)

    # 图片
    if corner_radius > 0:
        mask = Image.new("L", (iw, ih), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, iw, ih], corner_radius, fill=255)
        canvas.paste(img, (pad, pad), mask=mask)
    else:
        canvas.paste(img, (pad, pad), mask=img)

    return canvas.convert("RGB")


def make_9grid(img, output_size=(1080, 1080), gap=4, bg_color="#FFFFFF"):
    try:
        bg_rgb = tuple(int(bg_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        bg_rgb = (255, 255, 255)

    # 裁剪为正方形
    ow, oh = img.size
    side = min(ow, oh)
    left = (ow - side) // 2
    top = (oh - side) // 2
    img = img.crop((left, top, left + side, top + side))

    cell_side = side // 3
    cells = []
    for row in range(3):
        for col in range(3):
            x1 = col * cell_side
            y1 = row * cell_side
            x2 = x1 + cell_side
            y2 = y1 + cell_side
            cells.append(img.crop((x1, y1, x2, y2)))

    tw, th = output_size
    cell_w = (tw - gap * 4) // 3
    cell_h = (th - gap * 4) // 3
    cell_size = min(cell_w, cell_h)

    canvas = Image.new("RGB", (tw, th), bg_rgb)
    for idx, cell in enumerate(cells):
        row, col = divmod(idx, 3)
        resized = cell.resize((cell_size, cell_size), Image.LANCZOS)
        x = gap + col * (cell_size + gap)
        y = gap + row * (cell_size + gap)
        canvas.paste(resized, (x, y))

    return canvas


def remove_watermark(img, x, y, w, h, inpaint_radius=5):
    open_cv = img.convert("RGB")
    arr = np.array(open_cv)
    arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    mask = np.zeros(arr.shape[:2], dtype=np.uint8)
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(arr.shape[1], x + w), min(arr.shape[0], y + h)
    mask[y1:y2, x1:x2] = 255

    result = cv2.inpaint(arr, mask, inpaint_radius, cv2.INPAINT_TELEA)
    result = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
    return Image.fromarray(result)
