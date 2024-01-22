import React from 'react';
import { useMemo } from 'react';

import ServicePane from '../panels/ServicePane';
import FieldGroup from '../../common/FieldGroup';
import DroppableNodeList from '../panels/DroppableNodeList';
import CreatableService from '../panels/CreatableService';

import { useQueryQuery, useMemoizeWhenFetched, swapLabels,
         createItemsSelector } from 'api/query';
import { getPath, useQueryState, useData } from '../panels/ServiceList';

const service = 'topology/ip-connectivity';
const queryKey = 'ip-connectivity';

const loopbackInterfaces = 'loopback-interfaces/loopback';

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
    'IP Connectivity Services': useQueryState(service, queryKey),
    'Loopback Interfaces': useQueryState(`${service}/${loopbackInterfaces}`)
  });
}

export function useQuery(itemSelector, managed) {
  return useQueryQuery({
    xpathExpr: getPath(!managed && service, managed),
    queryKey,
    selection: [
      managed ? 'topology' : '../name',
      'ipv6',
      ...Object.keys(selection),
      ...Object.keys(physicalInterfaces) ],
    tag: 'managed-topology'
  }, { selectFromResult: itemSelector });
}

export function Component({ topology }) {
  console.debug('IpConnectivity Render');

  const label = 'IP Connectivity Service';
  const [ data, tmpKp ] = useData(useQuery, topology, 'ipv6', 'parentName');
  const isManaged = data && 'name' in data;

  // This service keypath may not be returned by the query when there are no
  // values (not possible in any other services since they have keys).
  // Need to calculate the keypaths explicitly.
  const serviceKeypath = isManaged ? tmpKp :
    `${getPath('topology')}{${topology}}/ip-connectivity`;
  const keypath = isManaged ? data.keypath : serviceKeypath;

  const selector = useMemo(() => createItemsSelector(
    isManaged ? 'topology' : 'parentName', topology), [ isManaged, topology ]);

  return (data ?
    <ServicePane
      disableDelete={isManaged}
      { ...{ label, keypath, serviceKeypath, queryKey,
        ...swapLabels(data, selection) } }
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
