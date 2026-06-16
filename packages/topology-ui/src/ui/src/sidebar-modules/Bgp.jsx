import React from 'react';
import { useMemo } from 'react';

import DeviceList from 'features/menu/panels/DeviceList';
import ServicePane from 'features/menu/panels/ServicePane';

import { useQueryQuery, useMemoizeWhenFetched, swapLabels,
         createItemsSelector } from 'api/query';
import { useQueryState, useData } from 'features/menu/panels/ServiceList';

export const label = 'BGP Service';
export const service = 'bgp';
export const path = `/topology:topologies/${service}`;
export const stackedPath = `/topology:topologies/managed-topology/${service}`;
export const newItemContextLeaf = 'topology';

const peRouters = 'provider-edge/routers';
const lsRouters = 'link-state/routers';
const routerReflectors = 'route-reflector/routers';

const selection = {
  'provider-edge/loopback-id':    'PE Loopback',
  'link-state/loopback-id':       'Link-State Loopback',
  'route-reflector/loopback-id':  'Route Reflector Loopback'
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
    selection: ['as-number', 'topology', ...Object.keys(selection) ],
    tag: 'managed-topology'
  }, { selectFromResult: itemSelector });
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'BGP Services': useServiceQueryState(),
    'PE Routers': useServiceQueryState(peRouters),
    'Link-State Routers': useServiceQueryState(lsRouters),
    'Router Reflectors': useServiceQueryState(routerReflectors)
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
      label={label}
      keypath={keypath}
      serviceKeypath={serviceKeypath}
      { ...swapLabels(data, selection) }
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
