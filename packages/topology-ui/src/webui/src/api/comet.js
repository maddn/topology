import { jsonRpcApi } from './index';
import { updateQueryData } from './query';

export const unsubscribeAll = () => async (dispatch, getState) => {
  const state = getState();
  await Promise.all(
    cometApi.util.selectInvalidatedBy(state, [ 'subscription' ]).map(
      ({ originalArgs }) => dispatch(unsubscribe.initiate({
        handle: subscribe.select(originalArgs)(state).data.result.handle
      }))
    )
  );
};

export const stopThenGoToUrl = (url) => async (dispatch, getState) => {
  await unsubscribeAll();
  window.location.assign(url);
};

export const cometApi = jsonRpcApi.injectEndpoints({
  endpoints: (build) => ({

    comet: build.mutation({
      query: () => ({
        method: 'comet'
      }),
      async onQueryStarted(args, { dispatch, queryFulfilled }) {
        const notifications = await queryFulfilled;
        dispatch(comet.initiate());
        notifications.data?.result?.forEach(notification => {
          const { message } = notification;
          message.changes?.forEach(({ keypath, op, value }) => {
            if (op === 'value_set') {
              const [ , itemKeypath, leaf ] = keypath.match(/(.*)\/(.*)/);
              dispatch(updateQueryData(itemKeypath, leaf, value));
            }
          });
        });
      }
    }),

    subscribe: build.query({
      query: ({ path }) => ({
        method: 'subscribe_cdboper',
        params: { path: path },
      }),
      providesTags: ['subscription'],
      async onQueryStarted(args, { dispatch, queryFulfilled }) {
        const response = await queryFulfilled;
        dispatch(startSubscription.initiate(
          { handle: response.data.result.handle }));
      }
    }),

    startSubscription: build.mutation({
      query: ({ handle }) => ({
        method: 'start_subscription',
        params: { handle: handle },
      }),
    }),

    unsubscribe: build.mutation({
      query: ({ handle }) => ({
        method: 'unsubscribe',
        params: { handle: handle },
      }),
    })

  })
});

const { endpoints: { comet, startSubscription } } = cometApi;
export const { endpoints: { subscribe, unsubscribe } } = cometApi;
