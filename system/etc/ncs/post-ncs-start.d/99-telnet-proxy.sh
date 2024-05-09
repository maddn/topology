#!/bin/sh

nohup node /opt/ncs/packages/topology-ui/webui/telnet-proxy.js > /tmp/telnet-proxy.out 2&>1 &
