#docker build -t function-c .
FROM ubuntu:c
COPY run.c /home
WORKDIR /home
RUN gcc run.c -o run
