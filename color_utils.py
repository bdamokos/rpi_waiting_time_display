from functools import lru_cache


@lru_cache(maxsize=1024)
def find_optimal_colors(pixel_rgb, epd):
    """Find optimal combination of available colors to represent an RGB value"""
    r, g, b = pixel_rgb[:3]

    # Get available colors, falling back to BLACK if colors aren't supported
    has_red = hasattr(epd, 'RED')
    has_yellow = hasattr(epd, 'YELLOW')

    # Calculate color characteristics
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    saturation = max(r, g, b) - min(r, g, b)
    red_ratio = r / 255.0
    yellow_ratio = min(r, g) / 255.0  # Yellow needs both red and green

    # For black and white only displays
    if not (has_red or has_yellow):
        if luminance > 0.7:
            return [('white', 0.7), ('black', 0.3)]
        elif luminance > 0.3:
            return [('white', 0.5), ('black', 0.5)]
        else:
            return [('black', 0.7), ('white', 0.3)]

    # For displays with red support
    if has_red and not has_yellow:
        if r > 200 and g < 100:  # Strong red
            return [('red', 0.7), ('black', 0.2), ('white', 0.1)]
        elif saturation < 30:  # Grayscale
            if luminance > 0.7:
                return [('white', 0.7), ('black', 0.3)]
            elif luminance > 0.3:
                return [('white', 0.5), ('black', 0.5)]
            else:
                return [('black', 0.7), ('white', 0.3)]
        elif r > g and r > b:  # Reddish
            return [('red', 0.6), ('black', 0.2), ('white', 0.2)]
        else:
            return [('black', 0.6), ('white', 0.4)]

    # For displays with yellow support (and possibly red)
    if has_yellow:
        if r > 200 and g < 100:  # Strong red
            return [('red', 0.7), ('black', 0.2), ('white', 0.1)] if has_red else [('black', 0.7), ('white', 0.3)]
        elif r > 200 and g > 200:  # Strong yellow
            return [('yellow', 0.7), ('black', 0.2), ('white', 0.1)]
        elif saturation < 30:  # Grayscale
            if luminance > 0.7:
                return [('white', 0.7), ('black', 0.3)]
            elif luminance > 0.3:
                return [('white', 0.5), ('black', 0.5)]
            else:
                return [('black', 0.7), ('white', 0.3)]
        elif r > g and r > b:  # Reddish
            return [('red', 0.6), ('black', 0.2), ('white', 0.2)] if has_red else [('black', 0.6), ('white', 0.4)]
        elif r > 100 and g > 100:  # Yellowish
            return [('yellow', 0.6), ('black', 0.2), ('white', 0.2)]
        else:
            return [('black', 0.6), ('white', 0.4)]

    # Default fallback
    return [('black', 0.6), ('white', 0.4)]