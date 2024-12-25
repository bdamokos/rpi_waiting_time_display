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
    orange_factor = min(r, g) / max(1, r) if r > 0 else 0  # How "yellow" is the orange

    # Handle pure white specially
    if r > 250 and g > 250 and b > 250:
        return [('white', 1.0)]

    # Handle pure black specially
    if r < 5 and g < 5 and b < 5:
        return [('black', 1.0)]

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
            red_strength = (r - g) / 255.0
            return [('red', 0.6 + red_strength * 0.2), ('black', 0.2), ('white', 0.2)]
        elif saturation < 30:  # Grayscale
            if luminance > 0.7:
                return [('white', 0.7), ('black', 0.3)]
            elif luminance > 0.3:
                return [('white', 0.5), ('black', 0.5)]
            else:
                return [('black', 0.7), ('white', 0.3)]
        elif r > g and r > b:  # Reddish
            red_dominance = (r - max(g, b)) / 255.0
            return [('red', 0.5 + red_dominance * 0.3), ('black', 0.3), ('white', 0.2)]
        else:
            return [('black', 0.6), ('white', 0.4)]

    # For displays with yellow support (and possibly red)
    if has_yellow:
        if r > 200 and g < 100:  # Strong red
            if has_red:
                red_strength = (r - g) / 255.0
                white_ratio = max(0.1, min(0.3, luminance))
                black_ratio = max(0.1, 1.0 - red_strength - white_ratio)
                return [('red', red_strength), ('black', black_ratio), ('white', white_ratio)]
            else:
                return [('black', 0.7), ('white', 0.3)]
        elif r > 200 and g > 200:  # Strong yellow
            yellow_strength = min(r, g) / 255.0
            white_ratio = max(0.1, min(0.3, luminance))
            black_ratio = max(0.1, 1.0 - yellow_strength - white_ratio)
            return [('yellow', yellow_strength), ('black', black_ratio), ('white', white_ratio)]
        elif saturation < 30:  # Grayscale
            if luminance > 0.7:
                return [('white', 0.7), ('black', 0.3)]
            elif luminance > 0.3:
                return [('white', 0.5), ('black', 0.5)]
            else:
                return [('black', 0.7), ('white', 0.3)]
        elif r > g and r > b and g < 100:  # Pure reddish
            if has_red:
                red_dominance = (r - max(g, b)) / 255.0
                white_ratio = max(0.1, min(0.3, luminance))
                black_ratio = max(0.1, 1.0 - red_dominance - white_ratio)
                return [('red', red_dominance), ('black', black_ratio), ('white', white_ratio)]
            else:
                return [('black', 0.6), ('white', 0.4)]
        elif r > 100 and g > 100:  # Yellowish or orange
            if r > g:  # Orange (mix of yellow and red)
                if has_red:
                    # Calculate how much yellow vs red to use based on the orange_factor
                    yellow_amount = orange_factor * 0.5
                    red_amount = (1 - orange_factor) * 0.5
                    black_amount = max(0.1, 1.0 - yellow_amount - red_amount)
                    return [('yellow', yellow_amount), ('red', red_amount), ('black', black_amount)]
                else:
                    # Without red, use more yellow for orange colors
                    yellow_strength = orange_factor
                    white_ratio = max(0.1, min(0.3, luminance))
                    black_ratio = max(0.1, 1.0 - yellow_strength - white_ratio)
                    return [('yellow', yellow_strength), ('black', black_ratio), ('white', white_ratio)]
            else:  # More purely yellow
                yellow_strength = min(r, g) / 255.0
                white_ratio = max(0.1, min(0.3, luminance))
                black_ratio = max(0.1, 1.0 - yellow_strength - white_ratio)
                return [('yellow', yellow_strength), ('black', black_ratio), ('white', white_ratio)]
        else:
            return [('black', 0.6), ('white', 0.4)]

    # Default fallback
    return [('black', 0.6), ('white', 0.4)]