import React from 'react';
import { useMemo } from 'react';

import ServicePane from '../panels/ServicePane';
import FieldGroup from '../../common/FieldGroup';
import DroppableNodeList from '../panels/DroppableNodeList';

import { useQueryQuery, useMemoizeWhenFetched, swapLabels,
         createItemsSelector } from 'api/query';
import { getPath, useQueryState, useData } from '../panels/ServiceList';

export const label = 'Segment Routing Service';
export const service = 'segment-routing';
const flexAlgo = 'flex-algo';

const selection = {
  'prefix-sid-start': 'Prefix SID Start',
  'boolean(pce)':     'PCE Enabled'
};

const srv6 = {
  'boolean(srv6)':              'SRv6 Enabled',
  'srv6/locator-prefix-start':  'Locator Prefix Start'
};

const srgb = {
  'srgb/lower-bound': 'Lower Bound',
  'srgb/upper-bound': 'Upper Bound'
};

export function useQuery(itemSelector, managed) {
  return useQueryQuery({
    xpathExpr: getPath(service, managed),
    selection: [
      'igp',
      'deref(igp)/../topology',
      ...Object.keys(selection),
      ...Object.keys(srgb),
      ...Object.keys(srv6) ],
    tag: 'managed-topology'
  }, itemSelector ? { selectFromResult: itemSelector } : undefined);
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'Segment Routing Services': useQueryState(service),
    'Flex Algos': useQueryState(`${service}/${flexAlgo}`)
  });
}

export const Component = React.memo(function Component({ name }) {
  console.debug('SegmentRouting Render');

  const [ data, serviceKeypath ] = useData(useQuery, name);
  const selector = useMemo(() => createItemsSelector('igp', name), [ name ]);
  const { keypath, topology } = data;

  return (
    <ServicePane
      key={name}
      title={`IGP ${name}`}
      serviceKeypath={serviceKeypath}
      { ...{ label, keypath, topology, ...swapLabels(data, selection) }}
    >
      <FieldGroup title="SRGB" { ...swapLabels(data, srgb) } />
      <DroppableNodeList
        label="Flex Algo"
        keypath={`${keypath}/${flexAlgo}`}
        baseSelect={[ 'id', '../igp', ]}
        labelSelect={{
          'boolean(metric-type-delay)': 'Metric Type Delay',
          'affinity-exclude':           'Affinity Exclude',
          'srv6-locator':               'SRv6 Locator'
        }}
        selector={selector}
     />
     <FieldGroup title="SRv6" { ...swapLabels(data, srv6) } />
   </ServicePane>
  );
});
