import './topology.css';

import React from 'react';
import { useSelector, useDispatch } from 'react-redux';
import classNames from 'classnames';

import TopologyBody from './TopologyBody';
import ToggleButton from './ToggleButton';
import IconSizeSlider from './IconSizeSlider';

import { getDraggedItem,
         getEditMode, editModeToggled,
         getConfigViewerVisible, configViewerToggled,
         getLinkMetricsVisible, linkMetricsToggled
} from './topologySlice';


function TopologyVisualiser () {
  console.debug('TopologyVisualiser Render');

  const draggedItem = useSelector((state) => getDraggedItem(state));
  const editMode = useSelector((state) => getEditMode(state));
  const configViewerVisible = useSelector((state) =>
    getConfigViewerVisible(state));
  const linkMetricsVisible = useSelector((state) =>
    getLinkMetricsVisible(state));

  const dispatch = useDispatch();

  return (
    <div className={classNames('topology', {
      'topology--edit-mode': editMode,
      'topology--expanded': !configViewerVisible
    })}>
      <div className="topology__body">
        <TopologyBody/>
      </div>
      <div className="footer topology__footer">
        <ToggleButton
          handleToggle={(value) => {dispatch(editModeToggled(value));}}
          checked={editMode}
          label="Edit Topology"
          />
        <ToggleButton
          handleToggle={(value) => {dispatch(configViewerToggled(value));}}
          checked={configViewerVisible}
          label="Show Device Config"
          />
        <ToggleButton
          handleToggle={(value) => {dispatch(linkMetricsToggled(value));}}
          checked={linkMetricsVisible}
          label="Show Link Metrics"
          />
        <IconSizeSlider/>
        <div className={classNames('container__layer', 'container__overlay', {
          'container__overlay--inactive': draggedItem
        })}/>
      </div>
    </div>
  );
}

export default TopologyVisualiser;
