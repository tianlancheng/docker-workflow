#docker build -t function-g .
FROM ubuntu:c
COPY run.c /home
WORKDIR /home
RUN gcc run.c -o run
