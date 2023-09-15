import React from 'react';
import { useMemo } from 'react';

import ServicePane from '../panels/ServicePane';
import FieldGroup from '../../common/FieldGroup';
import DroppableNodeList from '../panels/DroppableNodeList';
import CreatableService from '../panels/CreatableService';

import { useQueryQuery, useQueryState, useMemoizeWhenFetched, swapLabels,
         selectItem, createItemsSelector } from 'api/query';

const topologyPath = '/topology:topologies/topology';
const ipConnectivity = 'ip-connectivity';
const loopbackInterfaces = 'loopback-interfaces/loopback';
const path = `${topologyPath}/${ipConnectivity}`;

const selection = {
  'boolean(ipv6)': 'IPv6'
};

const physicalInterfaces = {
  'boolean(physical-interfaces)':           'Config IP Addresses',
  'physical-interfaces/ipv4-subnet-start':  'IPv4 Subnet Start',
  'physical-interfaces/ipv6-subnet-start':  'IPv6 Subnet Start'
};

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'IP Connectivity Services': useQueryState(path),
    'Loopback Interfaces': useQueryState(`${path}/${loopbackInterfaces}`)
  });
}

export function useQuery(itemSelector) {
  return useQueryQuery({
    xpathExpr: path,
    selection: [
      '../name',
      'ipv6',
      ...Object.keys(selection),
      ...Object.keys(physicalInterfaces) ],
  }, { selectFromResult: itemSelector });
}

export function Component({ topology }) {
  console.debug('IpConnectivity Render');

  const label = 'IP Connectivity Service';
  const keypath = `${topologyPath}{${topology}}/${ipConnectivity}`;

  const { data } = useQuery(selectItem('parentName', topology));
  const selector = useMemo(() => createItemsSelector('parentName', topology), [ topology ]);

  return (data ?
    <ServicePane { ...{ label, keypath, ...swapLabels(data, selection) } }>
      <DroppableNodeList
        label="Loopback Interface"
        keypath={`${keypath}/${loopbackInterfaces}`}
        baseSelect={[ 'id', '../../../name' ]}
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
