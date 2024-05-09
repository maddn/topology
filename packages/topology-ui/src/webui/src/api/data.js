import { jsonRpcApi } from './index';
import { updateQueryData } from './query';

export const dataApi = jsonRpcApi.injectEndpoints({
  endpoints: (build) => ({

    getValue: build.query({
      query: (keypath) => ({
        method: 'get_value',
        transType: 'read',
        params: {
          path: keypath
        }
      }),
      providesTags: [ 'data' ],
      transformResponse: (response) => response?.result?.value
    }),

    setValue: build.mutation({
      query: ({ keypath, actionPath, leaf, value }) => ({
        method: 'set_value',
        actionPath,
        params: {
          path: `${actionPath || keypath}/${leaf}`,
          value: value
        }
      }),
      async onQueryStarted(
        { keypath, actionPath, leaf, value }, { dispatch, queryFulfilled }
      ){
        if (!actionPath) {
          await queryFulfilled;
          dispatch(updateQueryData(keypath, leaf, value));
        }
      }
    }),

    create: build.mutation({
      query: ({ name, keypath, ...rest }) => ({
        method: 'create',
        transType: 'read_write',
        params: {
          path: name ? `${keypath}{${name}}` : keypath
        }
      }),
      async onQueryStarted(
        { name, keypath, ...rest }, { dispatch, queryFulfilled }
      ){
        await queryFulfilled;
        dispatch(updateQueryData(`${keypath}{${name}}`, name, rest));
      }
    }),

    deletePath: build.mutation({
      query: ({ keypath }) => ({
        method: 'delete',
        transType: 'read_write',
        params: {
          path: keypath
        }
      }),
      invalidatesTags: (_, __, { tag }) => tag ? [ tag ] : [],
      async onQueryStarted({ keypath, queryKey }, { dispatch, queryFulfilled }) {
        await queryFulfilled;
        dispatch(updateQueryData(keypath, undefined, undefined, queryKey));
      }
    }),

    action: build.mutation({
      query: ({ transType, path, params }) => ({
        method: 'action',
        transType,
        params: { path, params }
      }),
      transformResponse: (response) => {
        if (Array.isArray(response?.result)) {
          return response?.result.reduce(
            (accumulator, { name, value }) => {
              accumulator[name] = value;
              return accumulator;
            }, {}
          )
        } else {
          return response?.result;
        }
      }
    }),

  })
});

export const {
  endpoints: { action, create, setValue },
  useGetValueQuery, useSetValueMutation,
  useCreateMutation, useDeletePathMutation,
  useActionMutation
} = dataApi;
