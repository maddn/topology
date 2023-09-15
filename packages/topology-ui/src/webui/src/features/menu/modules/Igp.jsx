import React from 'react';
import { useMemo } from 'react';

import ServicePane from '../panels/ServicePane';
import DeviceList from '../panels/DeviceList';

import { useQueryQuery, useQueryState, useMemoizeWhenFetched,
         selectItem, createItemsSelector } from 'api/query';

export const label = 'IGP Service';
export const path = '/topology:topologies/igp';
const devices = 'devices';

export function useQuery(itemSelector) {
  return useQueryQuery({
    xpathExpr : path,
    selection : ['name', 'topology', 'boolean(is-is)', 'boolean(ospf)']
  }, { selectFromResult: itemSelector });
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'IGP Services': useQueryState(path),
    'IGP Devices': useQueryState(`${path}/${devices}`)
  });
}

export function Component ({ name, fetching }) {
  console.debug('Igp Render');

  const { data } = useQuery(selectItem('name', name));
  const selector = useMemo(() => createItemsSelector('parentName', name), [ name ]);
  const { keypath, topology, isIs, ospf } = data;

  return (
    <ServicePane
      key={name}
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
