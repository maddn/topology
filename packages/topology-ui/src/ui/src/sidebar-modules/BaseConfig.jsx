import React from 'react';
import { useMemo } from 'react';

import ServicePane from 'features/menu/panels/ServicePane';
import FieldGroup from 'features/common/FieldGroup';
import DroppableNodeList from 'features/menu/panels/DroppableNodeList';
import CreatableService from 'features/menu/panels/CreatableService';

import { useQueryQuery, useMemoizeWhenFetched, swapLabels,
         createItemsSelector } from 'api/query';
import { useQueryState, useData } from 'features/menu/panels/ServiceList';

export const label = 'Base Config Service';
export const service = 'base-config';
export const path = `/topology:topologies/${service}`;
export const stackedPath = '/topology:topologies/managed-topology';
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

function useServiceQueryState(suffix, queryKey) {
  return useQueryState(
    suffix ? `${path}/${suffix}` : path,
    suffix ? `${stackedPath}/${suffix}` : stackedPath,
    queryKey
  );
}

export function useQuery(itemSelector, stacked) {
  return useQueryQuery({
    xpathExpr: stacked ? stackedPath : path,
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
    'Base Config Services': useServiceQueryState(undefined, queryKey),
    'SNMP Servers': useServiceQueryState(snmpServers),
    'Static Routes': useServiceQueryState(staticRoutes)
  });
}

export function Component({ topology }) {
  console.debug('BaseConfig Render');

  const [ data, serviceKeypath ] = useData(
     useQuery, topology, Object.keys(selection)[0]);
  const keypath = data?.keypath;

  const snmpSelector = useMemo(() =>
    createItemsSelector('topology', topology), [ topology ]);
  const routesSelector = useMemo(() =>
    createItemsSelector('topology', topology), [ topology ]);

  return (data ?
    <ServicePane
      label={label}
      keypath={keypath}
      serviceKeypath={serviceKeypath}
      disableDelete={keypath !== serviceKeypath}
      queryKey={queryKey}
      { ...swapLabels(data, selection) }
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
      keypath: `${path}{${topology}}` } } />
  );
}
