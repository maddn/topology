import React from 'react';
import { useMemo } from 'react';

import ServicePane from '../panels/ServicePane';
import DeviceList from '../panels/DeviceList';

import { useQueryQuery, useMemoizeWhenFetched,
         createItemsSelector } from 'api/query';
import { getPath, useQueryState, useData } from '../panels/ServiceList';

export const label = 'IGP Service';
export const service = 'igp';
export const setTopologyInNewItem = true;

const devices = 'devices';

export function useQuery(itemSelector, managed) {
  return useQueryQuery({
    xpathExpr : getPath(service, managed),
    selection : [ 'name', 'topology', 'boolean(is-is)', 'boolean(ospf)' ],
    tag: 'managed-topology'
  }, { selectFromResult: itemSelector });
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'IGP Services': useQueryState(service),
    'IGP Devices': useQueryState(`${service}/${devices}`)
  });
}

export function Component ({ name, fetching }) {
  console.debug('Igp Render');

  const [ data, serviceKeypath ] = useData(useQuery, name);
  const selector = useMemo(() => createItemsSelector('parentName', name), [ name ]);
  const { keypath, topology, isIs, ospf } = data;

  return (
    <ServicePane
      key={name}
      serviceKeypath={serviceKeypath}
      title={`Domain ${name}`} { ...{
        label, keypath, topology,
        'Routing Protocol': isIs ? 'IS-IS' : ospf ? 'OSPF' : '' } }
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
