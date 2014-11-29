#!/usr/bin/env python

import sys
import os
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()

setup(name='climaX',
      version='0.1.1',
      description='Collection for processing climate data for agricultural studies',
      long_description=README,
      author='Christian Schudoma',
      author_email='',
      url='https://github.com/arne-cl/climaX',
      py_modules=['getClimateData', 'vpd_heatsum', 'queries', 'login'],
      scripts=['getClimateData.py', 'climax_batch.py'],
      license='MIT License',
      install_requires=['mysql-python', 'pyyaml', 'BeautifulSoup4'],
     )


