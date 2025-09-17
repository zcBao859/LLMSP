from setuptools import setup, find_packages

setup(
    name='opencompass',
    version='0.1.0',
    packages=find_packages(),
    package_data={
        'opencompass': [
            'configs/**/*.py',
            'configs/**/*.json',
        ],
    },
    include_package_data=True,
    zip_safe=False,
)