import './nso.css';

import React from 'react';
import { PureComponent } from 'react';
import { connect } from 'react-redux';
import Modal from 'react-modal';
import classNames from 'classnames';

import * as Layout from 'constants/Layout';

import Header from './Header';
import Footer from './Footer';

import { getError, getHasWriteTransaction, getCommitInProgress,
         getBodyOverlayVisible, handleError } from './nsoSlice';
import { getOpenTopologyName } from '../menu/menuSlice';

import { getSystemSetting } from 'api';
import { query } from 'api/query';


const mapStateToProps = state => ({
  error: getError(state),
  hasWriteTransaction: getHasWriteTransaction(state),
  commitInProgress: getCommitInProgress(state),
  bodyOverlayVisible: getBodyOverlayVisible(state),
  openTopology: getOpenTopologyName(state),
  version: getSystemSetting.select('version')(state).data?.result,
  user: getSystemSetting.select('user')(state).data?.result,
  applications: query.select({
      xpathExpr: '/webui:webui/webui-one:applications/application',
    selection: [ 'id', 'href', 'title', 'abbreviation', 'shortcut' ]
  })(state).data
});

const mapDispatchToProps = {
  handleError,
  getSystemSettingQuery: getSystemSetting.initiate,
  queryQuery: query.initiate
};

class WebuiOne extends PureComponent {
  constructor(props) {
    super(props);
    this.state = {
      user: '<username>',
      version: '<version>',
      applications: [{
        href  : Layout.COMMIT_MANAGER_URL,
        title : 'Commit manager',
        abbreviation   : 'C'
      }, {
        href  : Layout.CONFIGURATION_EDITOR_URL,
        title : 'Configuration editor',
        abbreviation   : 'E'
      }, {
        href  : Layout.ALARM_MANAGER_URL,
        title : 'Alarm manager',
        abbreviation   : 'A'
      }, {
        href  : Layout.DASHBOARD_URL,
        title : 'Dashboard',
        abbreviation   : 'B'
      }, {
        href  : Layout.DEVICE_MANAGER_URL,
        title : 'Device manager',
        abbreviation   : 'D'
      }, {
        href  : Layout.SERVICE_MANAGER_URL,
        title : 'Service manager',
        abbreviation   : 'S'
      }, {
        href  : Layout.PACKAGE_UPGRADE_URL,
        title : 'Package upgrade',
        abbreviation   : 'P'
      }, {
        href  : Layout.INSIGHTS_MANAGER_URL,
        title : 'Insights manager',
        abbreviation   : 'I'
      }]
    };
  }

  closeBodyOverlay = () => {
    const { setBodyOverlay } = this.props;
    setBodyOverlay(false);
  };

  clearError = () => {
    const { handleError } = this.props;
    handleError(undefined);
  };

  async componentDidMount() {
    const { getSystemSettingQuery, queryQuery } = this.props;
    await getSystemSettingQuery('version');
    await getSystemSettingQuery('user');
    await queryQuery({
      xpathExpr: '/webui:webui/webui-one:applications/application',
      selection: [ 'id', 'href', 'title', 'abbreviation', 'shortcut' ]
    });
  }

  render() {
    console.debug('NsoWrapper Render');
    const { user, version, applications } = this.props;
    const { children, error, hasWriteTransaction,
      commitInProgress, bodyOverlayVisible, openTopology } = this.props;
    return (
      <div className="nso-background">
        <Header
          user={user} version={version} title={openTopology || Layout.TITLE}
          commitInProgress={commitInProgress}
          hasWriteTransaction={hasWriteTransaction}
        />
          <div className="nso-body">
            <div className={classNames('nso-body__overlay', {
              'nso-body__overlay--visible': bodyOverlayVisible
            })}/>
            <div className="nso-body__content">{children}</div>
          </div>
        <Footer
          applications={[ ...this.state.applications, ...(applications || []) ]}
          current={Layout.TITLE}
          hasWriteTransaction={hasWriteTransaction}
        />
        <Modal
          isOpen={!!error}
          contentLabel="Error Message"
          onRequestClose={this.clearError}
          className="nso-modal__content"
          overlayClassName="nso-modal__overlay"
        >
          <div className="nso-modal__title">Oops! Something went wrong....</div>
          <div className="nso-modal__body">{error && error.title}</div>
          <div className="nso-modal__body">{error && error.message}</div>
          <div className="nso-modal__footer">
            <button className="nso-btn" onClick={this.clearError}>Close</button>
          </div>
        </Modal>
      </div>
    );
  }
}

export default connect(mapStateToProps, mapDispatchToProps)(WebuiOne);
