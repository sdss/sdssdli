FROM python:3.11-slim-bookworm

MAINTAINER Jose Sanchez-Gallego, gallegoj@uw.edu
LABEL org.opencontainers.image.source https://github.com/albireox/sdssdli

WORKDIR /opt

COPY . sdssdli

RUN pip3 install -U pip setuptools wheel
RUN cd sdssdli && pip3 install .
RUN rm -Rf sdssdli

ENTRYPOINT sdssdli start --debug
