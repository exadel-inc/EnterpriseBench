FROM ubuntu:22.04

LABEL maintainer="pkowalczyk@exadel.com"
ARG DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /workspace/EnterpriseBench
COPY . /workspace/EnterpriseBench

# Install all dependencies via centralized script
RUN chmod +x utils/install_dependencies.sh && \
    utils/install_dependencies.sh
RUN chmod +x utils/prepare_dataverse.sh

CMD ["/bin/bash"]