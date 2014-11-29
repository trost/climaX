#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: Arne Neumann <climax.programming@arne.cl>

"""
This script reads the parameters culture_id, flowering date, soil volume and
field capacity from a tab-separated file and writes climate data to a
tab-separated file (drought before flowering, drought after flowering,
cold-before, cold-after, heat-before, heat-after, light-before, light-after).
"""

import sys
import argparse
import warnings

from getClimateData import main
import login


def get_climate_data(parameter_line):
    """
    Parameters
    ----------
    parameter_line : str
        one line from a tab-separated file containing culture_id,
        flowering date, soil volume and field capacity

    Returns
    -------
    temp_stress_days, drought_stress_days, light_intensity
    """
    columns = parameter_line.split('\t')
    assert len(columns) == 4, "Line {0} in file {1} doesn't contain 4 columns"
    culture_id, date, soil_volume, field_capacity = parameter_line.split('\t')
    return main(cursor, int(culture_id), date, float(soil_volume),
                float(field_capacity))


def format_climate_data(climate_data):
    """
    formats climate data (temp_stress_days, drought_stress_days,
    light_intensity) for tab-separated output.
    """
    temp_stress_days, drought_stress_days, light_intensity = climate_data
    return '{0}\t{1}\t{2}\t{3}\t{4}\t{5}\t{6}\t{7}\n'.format(
        drought_stress_days[0], drought_stress_days[1],
        temp_stress_days[0], temp_stress_days[1], temp_stress_days[2],
        temp_stress_days[3], light_intensity[0], light_intensity[1])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-i', '--input_file', type=argparse.FileType('r'),
        help=("tsv-file containing culture_id, flowering date, soil volume "
              "and field capacity"))
    parser.add_argument(
        '-o', '--output_file', default=sys.stdout, type=argparse.FileType('w'),
        help=("tsv-file containing drought stress days (before/after "
              "flowering), cold stress days (before/after flowering), "
              "heat stress days (before/after flowering) and light sum "
              "(before/after flowering)"))
    args = parser.parse_args(sys.argv[1:])

    if not args.input_file:
        sys.exit(1)

    database = login.get_db()
    cursor = database.cursor()

    args.output_file.write(
        ('drought-before\tdrought-after\tcold-before\tcold-after\theat-before'
         '\theat-after\tlight-before\tlight-after\n'))

    for i, line in enumerate(args.input_file):
        try:
            climate_data = get_climate_data(line)
            args.output_file.write(format_climate_data(climate_data))
        except AssertionError as e:
            warnings.warn(e.message.format(i, args.input_file))
