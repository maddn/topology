import { createSlice } from '@reduxjs/toolkit';

// === Selectors ==============================================================

export const getOpenTopology = state => state.menu.openTopology;
export const getOpenService = state => state.menu.openService;

export const getOpenTopologyName = state =>
  getOpenTopology(state) &&  getOpenTopology(state).match(/{([^}]+)}$/)[1];


// === Reducer ================================================================

const menuSlice = createSlice({
  name: 'menu',
  initialState: {},
  reducers: {
    topologyToggled: (state, { payload }) => {
      state.openTopology = state.openTopology === payload ? undefined : payload;
    },
    serviceToggled: (state, { payload }) => {
      const { keypath } = payload;
      state.openService = state.openService === keypath ? undefined : keypath;
    },
  }
});

const { actions, reducer } = menuSlice;
export const { topologyToggled, serviceToggled } = actions;
export default reducer;
