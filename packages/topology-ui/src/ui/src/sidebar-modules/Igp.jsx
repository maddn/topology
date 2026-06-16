import React from 'react';
import { useMemo } from 'react';

import ServicePane from 'features/menu/panels/ServicePane';
import DeviceList from 'features/menu/panels/DeviceList';

import { useQueryQuery, useMemoizeWhenFetched,
         createItemsSelector } from 'api/query';
import { useQueryState, useData } from 'features/menu/panels/ServiceList';

export const label = 'IGP Service';
export const service = 'igp';
export const path = `/topology:topologies/${service}`;
export const stackedPath = `/topology:topologies/managed-topology/${service}`;
export const newItemContextLeaf = 'topology';

const devices = 'devices';

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
    selection: [ 'name', 'topology', 'boolean(is-is)', 'boolean(ospf)' ],
    tag: 'managed-topology'
  }, { selectFromResult: itemSelector });
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'IGP Services': useServiceQueryState(),
    'IGP Devices': useServiceQueryState(devices)
  });
}

export function Component({ name }) {
  console.debug('Igp Render');

  const [ data, serviceKeypath ] = useData(useQuery, name);
  const selector = useMemo(() => createItemsSelector('parentName', name), [ name ]);
  const { keypath, topology, isIs, ospf } = data;
  const serviceSelection = {
    'Routing Protocol': isIs ? 'IS-IS' : ospf ? 'OSPF' : ''
  };

  return (
    <ServicePane
      key={name}
      title={`Domain ${name}`}
      label={label}
      keypath={keypath}
      serviceKeypath={serviceKeypath}
      topology={topology}
      { ...serviceSelection }
    >
      <DeviceList
        label="Device"
        keypath={`${keypath}/${devices}`}
        select={[ '.', '../name' ]}
        selector={selector}
        isLeafList={true}
        parentName={name}
      />
    </ServicePane>
  );
}
