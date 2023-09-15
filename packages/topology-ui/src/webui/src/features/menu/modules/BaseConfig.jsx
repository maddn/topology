import React from 'react';
import { useMemo } from 'react';

import ServicePane from '../panels/ServicePane';
import FieldGroup from '../../common/FieldGroup';
import DroppableNodeList from '../panels/DroppableNodeList';
import CreatableService from '../panels/CreatableService';

import { useQueryQuery, useQueryState, useMemoizeWhenFetched, swapLabels,
         selectItem, createItemsSelector } from 'api/query';

const path = '/topology:topologies/base-config';
const snmpServers = 'snmp-server/host';
const staticRoutes = 'static-routes/route';

const selection = {
  'ntp-server':           'NTP Server',
  'interface-bandwidth':  'Interface Bandwidth',
  'boolean(lldp)':        'LLDP'
};

const logging = {
  'boolean(logging)':                 'Logging Enabled',
  'logging/syslog-server/ip-address': 'Syslog Server',
  'logging/syslog-server/port':       'Syslog Port'
};

const grpc = {
  'boolean(grpc)':  'GRPC Enabled',
  'grpc/port':      'GRPC Port'
};

const pce = {
  'pce/router':       'PCE Router',
  'pce/loopback-id':  'PCE Loopback ID',
  'pce/password':     'PCE Password'
};

const managementRoutes = {
  'static-routes/loopback-to-management/device':
    'Loopback to Management Device',
  'static-routes/loopback-to-management/loopback-id':
    'Loopback ID'
};

export function useQuery(itemSelector) {
  return useQueryQuery({
    xpathExpr: path,
    selection: [
      'topology',
      ...Object.keys(selection),
      ...Object.keys(logging),
      ...Object.keys(grpc),
      ...Object.keys(managementRoutes),
      ...Object.keys(pce) ]
  }, { selectFromResult: itemSelector });
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'Base Config Services': useQueryState(path),
    'SNMP Servers': useQueryState(`${path}/${snmpServers}`),
    'Static Routes': useQueryState(`${path}/${staticRoutes}`)
  });
}

export function Component({ topology }) {
  console.debug('BaseConfig Render');

  const label = 'Base Config Service';
  const keypath = `${path}{${topology}}`;

  const { data } = useQuery(selectItem('name', topology));
  const snmpSelector = useMemo(() =>
    createItemsSelector('topology', topology), [ topology ]);
  const routesSelector = useMemo(() =>
    createItemsSelector('topology', topology), [ topology ]);

  return (data ?
    <ServicePane { ...{ label, keypath, ...swapLabels(data, selection) } }>
      <FieldGroup title="Logging" { ...swapLabels(data, logging) } />
      <DroppableNodeList
        label="SNMP Server"
        keypath={`${keypath}/${snmpServers}`}
        baseSelect={[ 'ip-address', '../../topology' ]}
        labelSelect={{
          'port': 'Port',
          'community-string': 'Community String'
        }}
        selector={snmpSelector}
     />
      <FieldGroup title="GRPC" { ...swapLabels(data, grpc) } />
      <FieldGroup title="Static Routes" { ...swapLabels(data, managementRoutes) } />
      <DroppableNodeList
        label="Static Route"
        noTitle={true}
        disableCreate={true}
        keypath={`${keypath}/${staticRoutes}`}
        baseSelect={[
          `concat(source-device, " --> ",
                  destination-device, " : Loopback ",
                  loopback-id)`,
          '../../topology'
        ]}
        labelSelect={{
          'source-device':      'Source',
          'destination-device': 'Destination',
          'loopback-id':        'Loopback ID',
          'return-route':       'Return Route'
        }}
        selector={routesSelector}
      />
      <FieldGroup title="PCE" { ...swapLabels(data, pce) } />
    </ServicePane> :
    <CreatableService { ...{ label, keypath } } />
  );
}
