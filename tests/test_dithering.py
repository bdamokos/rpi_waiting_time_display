import pytest
from PIL import Image, ImageDraw, ImageFont
from display_adapter import DisplayAdapter, MockDisplay
from dithering import draw_dithered_box, draw_multicolor_dither
from color_utils import find_optimal_colors
import os
import textwrap

TEST_COLORS = [
    # Original colors
    "000000",  # Black
    "005CA5",  # Dark Blue
    "009EE3",  # Light Blue
    "4CA22F",  # Green
    "7B4400",  # Brown
    "8A236C",  # Purple
    "D0033F",  # Dark Red
    "E41F18",  # Red
    "ED6E86",  # Pink
    "EE7101",  # Orange
    "F9AB13",  # Light Orange
    "FFAA00",  # Orange Yellow
    "FFD800",  # Yellow
    # Additional colors
    "005460",  # Dark Teal
    "0056A4",  # Medium Blue
    "009CB4",  # Light Teal
    "00A6E2",  # Sky Blue
    "15882E",  # Forest Green
    "4A5321",  # Olive
    "69C0AC",  # Seafoam
    "70A3BD",  # Grayish Blue
    "822A3A",  # Burgundy
    "83D0F5",  # Light Sky Blue
    "8C2B87",  # Purple
    "A85E24",  # Brown
    "B59E6A",  # Tan
    "C8D300",  # Lime
    "E40521",  # Bright Red
    "E6007E",  # Magenta
    "EF7D00",  # Orange
    "F9C5B8",  # Light Pink
    "FC95C5",  # Pink
    "FFCC00",  # Golden Yellow
    "FFCC11",  # Golden Yellow
    "FFFFFF",  # White
]

def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple"""
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def create_sprite_sheet(display_type: str, results: list, output_dir: str):
    """Create a sprite sheet with all colors and their dithered versions"""
    # Configuration
    box_size = 60
    padding = 20
    text_height = 100
    # Now we have 3 boxes side by side: original, 2-color dither, multicolor dither
    pair_width = (box_size * 3) + (padding * 2)
    pairs_per_row = 2
    rows = (len(TEST_COLORS) + pairs_per_row - 1) // pairs_per_row

    # Calculate image dimensions
    width = (pair_width + padding * 2) * pairs_per_row
    height = (box_size + text_height + padding * 2) * rows

    # Create image
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    
    try:
        # Try to load a system font
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)
    except:
        try:
            # Fallback to a different system font path
            font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 12)
        except:
            # Final fallback to default font
            font = ImageFont.load_default()

    # Set up mock display
    os.environ['mock_display_type'] = display_type
    display = MockDisplay()

    # Draw each color set
    for i, hex_color in enumerate(TEST_COLORS):
        row = i // pairs_per_row
        col = i % pairs_per_row
        
        # Calculate position with more padding
        x = col * (pair_width + padding * 2) + padding
        y = row * (box_size + text_height + padding * 2) + padding
        
        # Draw original color
        rgb_color = hex_to_rgb(hex_color)
        draw.rectangle([x, y, x + box_size, y + box_size], fill=rgb_color)
        
        # Get colors for both methods
        colors_with_ratios = find_optimal_colors(rgb_color, display)
        
        # Draw two-color dithered version
        if len(colors_with_ratios) == 1:
            # Just fill with the single color
            color = colors_with_ratios[0][0]
            if color == 'black':
                fill_color = (0, 0, 0)
            elif color == 'white':
                fill_color = (255, 255, 255)
            elif color == 'red':
                fill_color = (255, 0, 0)
            else:  # yellow
                fill_color = (255, 255, 0)
            draw.rectangle([x + box_size + padding, y, x + box_size * 2 + padding, y + box_size], fill=fill_color)
        else:
            draw_dithered_box(
                draw=draw,
                epd=display,
                x=x + box_size + padding,
                y=y,
                width=box_size,
                height=box_size,
                text="",
                primary_color=colors_with_ratios[0][0],
                secondary_color=colors_with_ratios[1][0],
                ratio=colors_with_ratios[0][1],
                font=None
            )
        
        # Draw multicolor dithered version
        draw_multicolor_dither(
            draw=draw,
            epd=display,
            x=x + box_size * 2 + padding * 2,
            y=y,
            width=box_size,
            height=box_size,
            colors_with_ratios=colors_with_ratios
        )
        
        # Draw text
        text = f"#{hex_color}\n"
        text += "Two-color dither:\n"
        text += "\n".join(f"{color}: {ratio:.2f}" for color, ratio in colors_with_ratios[:2])
        text += "\nMulticolor dither:\n"
        text += "\n".join(f"{color}: {ratio:.2f}" for color, ratio in colors_with_ratios)
        
        # Draw text with white background for better readability
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = x + (pair_width - text_width) // 2
        text_y = y + box_size + padding
        
        # Draw white background for text with more padding
        padding_text = 8
        draw.rectangle([
            text_x - padding_text,
            text_y - padding_text,
            text_x + text_width + padding_text,
            text_y + text_height - padding_text
        ], fill='white', outline='lightgray')
        
        # Draw text
        draw.text((text_x, text_y), text, fill='black', font=font)

    # Save sprite sheet
    output_path = os.path.join(output_dir, f"sprite_sheet_{display_type}.png")
    image.save(output_path)
    return output_path

@pytest.mark.parametrize("display_type", ["bw", "bwr", "bwry"])
@pytest.mark.parametrize("hex_color", TEST_COLORS)
def test_color_dithering(display_type, hex_color, tmp_path):
    """Test dithering algorithm for each color in different display modes"""
    # Set up mock display type
    os.environ['mock_display_type'] = display_type
    display = MockDisplay()
    
    # Convert hex to RGB
    rgb_color = hex_to_rgb(hex_color)
    
    # Get optimal colors for dithering
    colors_with_ratios = find_optimal_colors(rgb_color, display)
    
    # Verify color count based on display type
    if display_type == "bw":
        assert len(colors_with_ratios) <= 2  # Should only use black and white
    elif display_type == "bwr":
        assert len(colors_with_ratios) <= 3  # Should use at most black, white, and red
    else:  # bwry
        assert len(colors_with_ratios) <= 4  # Should use at most black, white, red, and yellow
    
    # Verify ratios
    total_ratio = sum(ratio for _, ratio in colors_with_ratios)
    assert 0.99 <= total_ratio <= 1.01, f"Total ratio should be approximately 1.0 for {hex_color}"
    
    # All ratios should be between 0 and 1
    for _, ratio in colors_with_ratios:
        assert 0 <= ratio <= 1, f"Individual ratio should be between 0 and 1 for {hex_color}"

def test_color_ratios():
    """Test that color ratios are reasonable for each input color"""
    # Set up display with all colors
    os.environ['mock_display_type'] = "bwry"
    display = MockDisplay()
    
    results = []
    for hex_color in TEST_COLORS:
        rgb_color = hex_to_rgb(hex_color)
        colors_with_ratios = find_optimal_colors(rgb_color, display)
        
        # Store results for analysis
        results.append({
            'input_color': hex_color,
            'rgb_color': rgb_color,
            'output_colors': colors_with_ratios
        })
        
        # Basic ratio assertions
        total_ratio = sum(ratio for _, ratio in colors_with_ratios)
        assert 0.99 <= total_ratio <= 1.01, f"Total ratio should be approximately 1.0 for {hex_color}"
        
        # All ratios should be between 0 and 1
        for _, ratio in colors_with_ratios:
            assert 0 <= ratio <= 1, f"Individual ratio should be between 0 and 1 for {hex_color}"
    
    return results

if __name__ == "__main__":
    # Save images in a permanent test_output directory
    output_dir = "test_output"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate sprite sheets for each display type
    for display_type in ["bw", "bwr", "bwry"]:
        results = []
        for hex_color in TEST_COLORS:
            # Set up mock display type
            os.environ['mock_display_type'] = display_type
            display = MockDisplay()
            
            # Get color analysis
            rgb_color = hex_to_rgb(hex_color)
            colors_with_ratios = find_optimal_colors(rgb_color, display)
            
            results.append({
                'input_color': hex_color,
                'rgb_color': rgb_color,
                'output_colors': colors_with_ratios
            })
        
        # Create sprite sheet
        sprite_sheet_path = create_sprite_sheet(display_type, results, output_dir)
        print(f"Created sprite sheet for {display_type} display: {sprite_sheet_path}")
    
    # Save detailed color analysis to a text file
    with open(os.path.join(output_dir, "color_analysis.txt"), "w") as f:
        for display_type in ["bw", "bwr", "bwry"]:
            f.write(f"\n=== {display_type.upper()} Display ===\n")
            os.environ['mock_display_type'] = display_type
            display = MockDisplay()
            
            for hex_color in TEST_COLORS:
                rgb_color = hex_to_rgb(hex_color)
                colors_with_ratios = find_optimal_colors(rgb_color, display)
                
                f.write(f"\nInput: #{hex_color}\n")
                f.write(f"RGB: {rgb_color}\n")
                f.write("Output colors and ratios:\n")
                for color, ratio in colors_with_ratios:
                    f.write(f"  {color}: {ratio:.2f}\n")
            
    print(f"\nTest results have been saved to the '{output_dir}' directory.") 