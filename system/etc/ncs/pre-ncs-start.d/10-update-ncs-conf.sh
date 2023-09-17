#!/bin/sh

CONF_FILE=${CONF_FILE:-/etc/ncs/ncs.conf}

# update ports for various protocols for which the default value in ncs.conf is
# different from the protocols default port (to allow starting ncs without root)
# NETCONF call-home is already on its default 4334 since that's above 1024
xmlstarlet edit \
    --inplace -N x=http://tail-f.com/yang/tailf-ncs-config \
    --update '/x:ncs-config/x:webui/x:transport/x:tcp/x:port' --value '80' \
    --update '/x:ncs-config/x:webui/x:transport/x:ssl/x:port' --value '443' \
    --update '/x:ncs-config/x:netconf-north-bound/x:transport/x:ssh/x:port' --value '830' \
    $CONF_FILE

# enable SSH CLI, NETCONF over SSH northbound, NETCONF call-home and RESTCONF
xmlstarlet edit \
    --inplace -N x=http://tail-f.com/yang/tailf-ncs-config \
    --update '/x:ncs-config/x:cli/x:ssh/x:enabled' --value 'true' \
    --update '/x:ncs-config/x:netconf-north-bound/x:transport/x:ssh/x:enabled' --value 'true' \
    --update '/x:ncs-config/x:netconf-call-home/x:enabled' --value 'true' \
    --update '/x:ncs-config/x:restconf/x:enabled' --value 'true' \
    $CONF_FILE

# enable webUI with no TLS on port 80
xmlstarlet edit \
    --inplace -N x=http://tail-f.com/yang/tailf-ncs-config \
    --update '/x:ncs-config/x:webui/x:transport/x:tcp/x:enabled' --value 'true' \
    $CONF_FILE

# enable webUI with TLS on port 443
xmlstarlet edit \
    --inplace -N x=http://tail-f.com/yang/tailf-ncs-config \
    --update '/x:ncs-config/x:webui/x:transport/x:ssl/x:enabled' --value 'true' \
    $CONF_FILE

# switch to local auth per default
xmlstarlet edit \
    --inplace -N x=http://tail-f.com/yang/tailf-ncs-config \
    --update '/x:ncs-config/x:aaa/x:pam/x:enabled' --value 'false' \
    --update '/x:ncs-config/x:aaa/x:local-authentication/x:enabled' --value 'true' \
    $CONF_FILE

# increase action timeout
xmlstarlet edit \
    --inplace -N x=http://tail-f.com/yang/tailf-ncs-config \
    --subnode '/x:ncs-config' --type elem --name 'japi' \
    $CONF_FILE
xmlstarlet edit \
    --inplace -N x=http://tail-f.com/yang/tailf-ncs-config \
    --subnode '/x:ncs-config/x:japi' --type elem --name 'query-timeout' --value 'PT600S' \
    $CONF_FILE
