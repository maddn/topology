import { createSlice } from '@reduxjs/toolkit';

// === Selectors ==============================================================

export const getDimensions = state => state.topology.dimensions;
export const getDraggedItem = state => state.topology.draggedItem;
export const getHoveredIcon = state => state.topology.hoveredIcon;
export const getSelectedConnection = state => state.topology.selectedConnection;
export const getSelectedIcon = state => state.topology.selectedIcon;
export const getExpandedIcons = state => state.topology.expandedIcons;
export const getVisibleUnderlays = state => state.topology.visibleUnderlays;
export const getZoomedContainer = state => state.topology.zoomedContainer;
export const getEditMode = state => state.topology.editMode;
export const getConfigViewerVisible = state => state.topology.configViewerVisible;
export const getIconSize = state => state.topology.iconSize;
export const getHighlightedIcons = state => state.topology.highlightedIcons;


// === Reducer ================================================================

const topologySlice = createSlice({
  name: 'topology',
  initialState: {
    dimensions: { width: 0, height: 0 },
    expandedIcons: [],
    visibleUnderlays: [],
    editMode: false
  },
  reducers: {
    dimensionsChanged: (state, action) => {
      state.dimensions.width = action.payload.width;
      state.dimensions.height = action.payload.height;
    },

    itemDragged: (state, action) => {
      state.draggedItem = action.payload;
    },

    iconHovered: (state, { payload }) => {
      state.hoveredIcon = payload;
    },

    connectionSelected: (state, action) => {
      const { aEndDevice, zEndDevice } = action.payload || {};
      state.selectedConnection = state.selectedConnection &&
        state.selectedConnection.aEndDevice === aEndDevice &&
        state.selectedConnection.zEndDevice === zEndDevice ?
          undefined : { aEndDevice, zEndDevice },
      state.selectedIcon = null;
    },

    iconSelected: (state, action) => {
      state.selectedIcon = state.selectedIcon === action.payload
        ? undefined : action.payload;
      state.selectedConnection = null;
    },

    iconExpandToggled: (state, { payload }) => {
      state.expandedIcons = state.expandedIcons.includes(payload)
        ? state.expandedIcons.filter(icon => icon !== payload)
        : [ payload, ...state.expandedIcons ];
    },

    underlayToggled: (state, { payload }) => {
      state.visibleUnderlays = state.visibleUnderlays.includes(payload)
        ? state.visibleUnderlays.filter(container => container !== payload)
        : [ ...state.visibleUnderlays, payload ];
    },

    containerZoomToggled: (state, action) => {
      state.zoomedContainer = state.zoomedContainer === action.payload
        ? undefined : action.payload;
    },

    editModeToggled: (state, { payload }) => {
      state.editMode = payload;
      state.expandedIcons = [];
      state.bodyOverlayVisible = payload;
    },

    configViewerToggled: (state, { payload }) => {
      state.configViewerVisible = payload;
    },

    iconSizeChanged: (state, action) => {
      state.iconSize = action.payload;
    }
  },

  extraReducers: (builder) => {
    builder.addCase('menu/serviceToggled', (state, { payload }) => {
      const { highlightedIcons } = payload;
      state.highlightedIcons = highlightedIcons;
    });
  }
});

const { actions, reducer } = topologySlice;
export const {
  dimensionsChanged, itemDragged, iconHovered,
  connectionSelected, iconSelected, iconExpandToggled,
  underlayToggled, containerZoomToggled,
  editModeToggled, configViewerToggled, iconSizeChanged } = actions;
export default reducer;
