import React from 'react';
import { useMemo } from 'react';

import ServicePane from 'features/menu/panels/ServicePane';
import FieldGroup from 'features/common/FieldGroup';
import DroppableNodeList from 'features/menu/panels/DroppableNodeList';
import CreatableService from 'features/menu/panels/CreatableService';

import { useQueryQuery, useMemoizeWhenFetched, swapLabels,
         createItemsSelector } from 'api/query';
import { useQueryState, useData } from 'features/menu/panels/ServiceList';

export const label = 'IP Connectivity Service';
export const service = 'ip-connectivity';
export const path = `/topology:topologies/topology/${service}`;
export const stackedPath = '/topology:topologies/managed-topology';
const queryKey = service;

const loopbackInterfaces = 'loopback-interfaces/loopback';

const selection = {
  'boolean(ipv6)': 'IPv6'
};

const physicalInterfaces = {
  'boolean(physical-interfaces)':           'Config IP Addresses',
  'physical-interfaces/ipv4-subnet-start':  'IPv4 Subnet Start',
  'physical-interfaces/ipv6-subnet-start':  'IPv6 Subnet Start'
};

function useServiceQueryState(suffix, queryKey) {
  return useQueryState(
    suffix ? `${path}/${suffix}` : path,
    suffix ? `${stackedPath}/${suffix}` : stackedPath,
    queryKey
  );
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'IP Connectivity Services': useServiceQueryState(undefined, queryKey),
    'Loopback Interfaces': useServiceQueryState(loopbackInterfaces)
  });
}

export function useQuery(itemSelector, stacked) {
  return useQueryQuery({
    xpathExpr: stacked ? stackedPath : path,
    queryKey,
    selection: [
      stacked ? 'topology' : '../name',
      'ipv6',
      ...Object.keys(selection),
      ...Object.keys(physicalInterfaces) ],
    tag: 'managed-topology'
  }, { selectFromResult: itemSelector });
}

export function Component({ topology }) {
  console.debug('IpConnectivity Render');

  const [ data, tmpKp ] = useData(
    useQuery, topology, 'ipv6', 'parentName');
  const isManaged = data && 'name' in data;

  // This service keypath may not be returned by the query when there are no
  // values (not possible in any other services since they have keys).
  // Need to calculate the keypaths explicitly.
  const serviceKeypath = isManaged ? tmpKp :
    `/topology:topologies/topology{${topology}}/ip-connectivity`;
  const keypath = isManaged ? data.keypath : serviceKeypath;

  const selector = useMemo(() => createItemsSelector(
    isManaged ? 'topology' : 'ancestorName', topology), [ isManaged, topology ]);

  return (data ?
    <ServicePane
      label={label}
      keypath={keypath}
      serviceKeypath={serviceKeypath}
      disableDelete={isManaged}
      queryKey={queryKey}
      { ...swapLabels(data, selection) }
    >
      <DroppableNodeList
        label="Loopback Interface"
        keypath={`${keypath}/${loopbackInterfaces}`}
        baseSelect={[ 'id', isManaged ? '../../topology' : '../../../name' ]}
        labelSelect={{
          'ipv4-subnet-start':  'IPv4 Subnet Start',
          'ipv6-subnet-start':  'IPv6 Subnet Start',
          'boolean(primary)':   'Primary'
        }}
        selector={selector}
      />
      <FieldGroup
        title="Physical Interfaces" { ...swapLabels(data, physicalInterfaces) }
      />
    </ServicePane> :
    <CreatableService { ...{ label, keypath } }/>
  );
}
