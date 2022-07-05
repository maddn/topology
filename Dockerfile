FROM debian:bullseye AS nso-build

RUN apt-get update \
  && echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections \
  && apt-get install -qy --no-install-recommends \
     ant \
     build-essential \
     default-jre-headless \
     iputils-ping \
     less \
     libexpat1 \
     libxml2-utils \
     libvirt-dev \
     openssh-client \
     make \
     pkg-config \
     python3 \
     python3-dev \
     python3-pip \
     procps \
     syslog-ng \
     tcpdump \
     telnet \
     vim-tiny \
     xsltproc \
     xmlstarlet \
  && pip3 install libvirt-python pycdlib \
  && apt-get -qy purge pkg-config python3-pip python3-dev \
  && apt-get -qy autoremove \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /root/.cache \
  && echo '. /opt/ncs/current/ncsrc' >> /root/.bashrc \
  # Add root to ncsadmin group for easier command-line tools usage
  && groupadd ncsadmin \
  && usermod -a -G ncsadmin root

ARG NSO_INSTALL_FILE
COPY $NSO_INSTALL_FILE /tmp/nso
RUN sh /tmp/nso --system-install --non-interactive && rm /tmp/nso

# default shell is ["/bin/sh", "-c"]. We add -l so we get a login shell which
# means the shell reads /etc/profile on startup. /etc/profile includes the files
# in /etc/profile.d where we have ncs.sh that sets the right paths so we can
# access ncsc and other NSO related tools. This makes it possible for
# Dockerfiles, using this image as a base, to directly invoke make for NSO
# package compilation.
SHELL ["/bin/sh", "-lc"]

COPY /system /
COPY /packages /build/packages
WORKDIR /opt/ncs

# Move and compile packages as follows:
# /opt/ncs/packages: packages initially present here have been precompiled and
# are left as is (not compiled again).

# /build/packages: this is the temporary location for the source packages. Each
# package is moved to /opt/ncs/packages and compiled (and stripped).

# /var/opt/ncs/packages: A symlink is created here to each package finally in
# /opt/ncs/packages.
RUN for pkg_src in $(ls /build/packages); do \
    mv /build/packages/${pkg_src} packages; \
    if [ -d packages/${pkg_src}/src ]; then \
      make -C packages/${pkg_src}/src || exit 1; \
    fi; \
  done; \
  for pkg in $(ls packages); do \
    ln -s /opt/ncs/packages/${pkg} /var/opt/ncs/packages; \
  done; \
  rm -rf /build;

# Remove stuff we don't need/want from the NSO installation \
RUN rm -rf \
  /opt/ncs/current/doc \
  /opt/ncs/current/erlang \
  /opt/ncs/current/examples.ncs \
  /opt/ncs/current/include \
  /opt/ncs/current/lib/ncs-project \
  /opt/ncs/current/lib/ncs/lib/confdc \
  /opt/ncs/current/lib/pyang \
  /opt/ncs/current/man \
  /opt/ncs/current/netsim/confd/erlang/econfd/doc \
  /opt/ncs/current/netsim/confd/src/confd/pyapi/doc \
  /opt/ncs/current/packages \
  /opt/ncs/current/src/aaa \
  /opt/ncs/current/src/build \
  /opt/ncs/current/src/cli \
  /opt/ncs/current/src/configuration_policy \
  /opt/ncs/current/src/errors \
  /opt/ncs/current/src/ncs/pyapi/doc \
  /opt/ncs/current/src/ncs_config \
  /opt/ncs/current/src/netconf \
  /opt/ncs/current/src/package-skeletons \
  /opt/ncs/current/src/project-skeletons \
  /opt/ncs/current/src/snmp \
  /opt/ncs/current/src/tools \
  /opt/ncs/current/src/yang

EXPOSE 22 80 443 830

HEALTHCHECK --start-period=60s --interval=5s --retries=3 --timeout=5s CMD /opt/ncs/current/bin/ncs_cmd -c get_phase

CMD ["/opt/ncs/run-nso.sh"]
