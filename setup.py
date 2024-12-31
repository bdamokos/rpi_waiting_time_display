from setuptools import setup, find_packages

setup(
    name="weather",
    version="0.1.0",
    packages=find_packages(),
    py_modules=['dithering', 'font_utils', 'display_adapter', 'astronomy_utils', 'log_config', 'color_utils', 'backoff'],
    install_requires=[
        "requests>=2.32.3",
        "pydantic>=2.5.0",
        "python-dotenv>=1.0.1",
        "cairosvg>=2.7.1",
        "Pillow>=11.0.0",
    ],
) 