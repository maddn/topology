import React from 'react';
import { useMemo } from 'react';

import DeviceList from '../panels/DeviceList';
import ServicePane from '../panels/ServicePane';

import { useQueryQuery, useMemoizeWhenFetched, swapLabels,
         createItemsSelector } from 'api/query';
import { getPath, useQueryState, useData } from '../panels/ServiceList';

export const label = 'BGP Service';
export const service = 'bgp';
export const setTopologyInNewItem = true;

const peRouters = 'provider-edge/routers';
const lsRouters = 'link-state/routers';
const routerReflectors = 'route-reflector/routers';

const selection = {
  'provider-edge/loopback-id':    'PE Loopback',
  'link-state/loopback-id':       'Link-State Loopback',
  'route-reflector/loopback-id':  'Route Reflector Loopback'
};

export function useQuery(itemSelector, managed) {
  return useQueryQuery({
    xpathExpr : getPath(service, managed),
    selection : ['as-number', 'topology', ...Object.keys(selection) ],
    tag: 'managed-topology'
  }, { selectFromResult: itemSelector });
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'BGP Services': useQueryState(service),
    'PE Routers': useQueryState(`${service}/${peRouters}`),
    'Link-State Routers': useQueryState(`${service}/${lsRouters}`),
    'Router Reflectors': useQueryState(`${service}/${routerReflectors}`)
  });
}

export function Component({ name }) {
  console.debug('Bgp Render');

  const [ data, serviceKeypath ] = useData(useQuery, name);
  const peSelector = useMemo(() => createItemsSelector('asNumber', name), [ name ]);
  const lsSelector = useMemo(() => createItemsSelector('asNumber', name), [ name ]);
  const rrSelector = useMemo(() => createItemsSelector('asNumber', name), [ name ]);
  const { keypath } = data;

  return (
    <ServicePane
      key={name}
      title={`AS ${name}`}
      serviceKeypath={serviceKeypath}
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
