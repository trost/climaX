#!/usr/bin/env python

import sys
import os
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()

setup(name='climaX',
      version='0.1.1',
      description='Collection for processing climate data for agricultural studies',
      long_description=README,
      author='Christian Schudoma',
      author_email='',
      url='https://github.com/arne-cl/climaX',
      packages=find_packages("src"),
      package_dir = {'': "src"},include_package_data=True,
      zip_safe=False,
      entry_points={
        'console_scripts':
          ['getClimateData=climax.climate_data:main']
      },
#      py_modules=['getClimateData', 'vpd_heatsum', 'queries', 'login'],
#      scripts=['getClimateData.py', 'climax_batch.py'],
      license='MIT License',
      install_requires=['mysql-python', 'pyyaml', 'BeautifulSoup4'],
     )


