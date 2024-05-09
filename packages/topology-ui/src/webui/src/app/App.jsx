import React from 'react';
import { PureComponent } from 'react';
import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';

import WebuiOne from 'features/nso/WebuiOne';
import MenuSidebar from 'features/menu/MenuSidebar';
import TopologyVisualiser from 'features/topology/TopologyVisualiser';
import ConfigViewer from 'features/config/ConfigViewer';
import TerminalViewer from 'features/terminal/TerminalViewer';

class App extends PureComponent {
  render() {
    console.debug('App Render');
    return (
      <DndProvider backend={HTML5Backend}>
        <WebuiOne>
          <MenuSidebar/>
          <div className="centre-pane">
            <TopologyVisualiser/>
            <TerminalViewer/>
          </div>
          <ConfigViewer/>
        </WebuiOne>
      </DndProvider>
    );
  }
}

export default App;
