from setuptools import setup, find_packages, findall

# Pull version from source without importing
# since we can't import something we haven't built yet :)
exec(open('adafruit/pieyes/version.py').read())

with open('README.md') as f:
    README = f.read()

setup(
    name="adafruit.pyeyes",
    version=__version__,
    packages=find_packages(exclude=['test']),
    scripts=findall('scripts/'),
    package_data={},
    author="Phillip Burgess",
    author_email="paintyourdragon@dslextreme.com",
    url="https://github.com/adafruit/Pi_Eyes",
    description="",
    long_description=README,
    install_requires=[
        'numpy',
        'pi3d',
        'svg.path',
        'adafruit-ads1x15',
        'RPi.GPIO',
        'pillow'
    ]
)
