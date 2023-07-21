#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-07-21
# @Filename: __main__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import click


@click.group()
def sdssdli():
    """SDSS DLI CLI."""

    pass


def main():
    sdssdli()


if __name__ == "__main__":
    main()
