import React from 'react';
import { useMemo } from 'react';

import ServicePane from '../panels/ServicePane';
import FieldGroup from '../../common/FieldGroup';
import DroppableNodeList from '../panels/DroppableNodeList';
import CreatableService from '../panels/CreatableService';

import { useQueryQuery, useMemoizeWhenFetched, swapLabels,
         createItemsSelector } from 'api/query';
import { getPath, useQueryState, useData } from '../panels/ServiceList';

const service = 'base-config';
const queryKey = service;

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

export function useQuery(itemSelector, managed) {
  return useQueryQuery({
    xpathExpr: getPath(!managed && service, managed),
    queryKey,
    selection: [
      'topology',
      ...Object.keys(selection),
      ...Object.keys(logging),
      ...Object.keys(grpc),
      ...Object.keys(managementRoutes),
      ...Object.keys(pce) ],
    tag: 'managed-topology'
  }, { selectFromResult: itemSelector });
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'Base Config Services': useQueryState(service, queryKey),
    'SNMP Servers': useQueryState(`${service}/${snmpServers}`),
    'Static Routes': useQueryState(`${service}/${staticRoutes}`)
  });
}

export function Component({ topology }) {
  console.debug('BaseConfig Render');

  const label = 'Base Config Service';

  const [ data, serviceKeypath ] = useData(
     useQuery, topology, Object.keys(selection)[0]);
  const keypath = data?.keypath;

  const snmpSelector = useMemo(() =>
    createItemsSelector('topology', topology), [ topology ]);
  const routesSelector = useMemo(() =>
    createItemsSelector('topology', topology), [ topology ]);

  return (data ?
    <ServicePane
      disableDelete={keypath !== serviceKeypath}
      { ...{ label, keypath, serviceKeypath, queryKey,
        ...swapLabels(data, selection) } }
    >
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
    <CreatableService { ...{ label,
      keypath: `${getPath(service)}{${topology}}` } } />
  );
}
