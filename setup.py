from setuptools import setup, find_packages


setup(
    name="neuralstyle",
    packages=find_packages(),
    install_requires=["tqdm>=4.23",
                      "torch>=0.3.0",
                      "torchvision>=0.2.1"]
)