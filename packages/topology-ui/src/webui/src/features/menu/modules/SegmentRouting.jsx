import React from 'react';
import { useMemo } from 'react';

import ServicePane from '../panels/ServicePane';
import FieldGroup from '../../common/FieldGroup';
import DroppableNodeList from '../panels/DroppableNodeList';

import { useQueryQuery, useQueryState, useMemoizeWhenFetched, swapLabels,
         selectItem, createItemsSelector } from 'api/query';

export const label = 'Segment Routing Service';
const path = '/topology:topologies/segment-routing';
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

export function useQuery(itemSelector) {
  return useQueryQuery({
    xpathExpr: path,
    selection: [
      'igp',
      'deref(igp)/../topology',
      ...Object.keys(selection),
      ...Object.keys(srgb),
      ...Object.keys(srv6) ],
  }, itemSelector ? { selectFromResult: itemSelector } : undefined);
}

export function useFetchStatus() {
  return useMemoizeWhenFetched({
    'Segment Routing Services': useQueryState(path),
    'Flex Algos': useQueryState(`${path}/${flexAlgo}`)
  });
}

export const Component = React.memo(function Component({ name }) {
  console.debug('SegmentRouting Render');

  const { data } = useQuery(selectItem('name', name));
  const selector = useMemo(() => createItemsSelector('igp', name), [ name ]);
  const { keypath, topology } = data;

  return (
    <ServicePane
      key={name}
      title={`IGP ${name}`}
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
