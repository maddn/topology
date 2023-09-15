import React from 'react';
import { useMemo } from 'react';

import DeviceList from '../panels/DeviceList';
import ServicePane from '../panels/ServicePane';

import { useQueryQuery, useQueryState, useMemoizeWhenFetched, swapLabels,
         selectItem, createItemsSelector } from 'api/query';

export const label = 'BGP Service';
const path = '/topology:topologies/bgp';
const peRouters = 'provider-edge/routers';
const lsRouters = 'link-state/routers';
const routerReflectors = 'route-reflector/routers';

const selection = {
  'provider-edge/loopback-id':    'PE Loopback',
  'link-state/loopback-id':       'Link-State Loopback',
  'route-reflector/loopback-id':  'Route Reflector Loopback'
};

export function useQuery(itemSelector) {
  return useQueryQuery({
    xpathExpr : path,
    selection : ['as-number', 'topology', ...Object.keys(selection) ]
  }, { selectFromResult: itemSelector });
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'BGP Services': useQueryState(path),
    'PE Routers': useQueryState(`${path}/${peRouters}`),
    'Link-State Routers': useQueryState(`${path}/${lsRouters}`),
    'Router Reflectors': useQueryState(`${path}/${routerReflectors}`)
  });
}

export function Component({ name }) {
  console.debug('Bgp Render');

  const { data } = useQuery(selectItem('name', name));
  const peSelector = useMemo(() => createItemsSelector('asNumber', name), [ name ]);
  const lsSelector = useMemo(() => createItemsSelector('asNumber', name), [ name ]);
  const rrSelector = useMemo(() => createItemsSelector('asNumber', name), [ name ]);
  const { keypath } = data;

  return (
    <ServicePane
      key={name}
      title={`AS ${name}`}
      { ...{ label, keypath, ...swapLabels(data, selection) } }
    >
      <DeviceList
        label="PE Router"
        keypath={`${keypath}/${peRouters}`}
        select={[ '.', '../../as-number' ]}
        selector={peSelector}
        asNumber={name}
      />
      <DeviceList
        label="Link-State Router"
        keypath={`${keypath}/${lsRouters}`}
        select={[ '.', '../../as-number' ]}
        selector={lsSelector}
        asNumber={name}
      />
      <DeviceList
        label="Route Reflector"
        keypath={`${keypath}/${routerReflectors}`}
        select={[ '.', '../../as-number' ]}
        selector={rrSelector}
        asNumber={name}
      />
    </ServicePane>
  );
}
