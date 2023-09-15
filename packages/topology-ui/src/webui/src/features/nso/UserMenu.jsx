import React from 'react';
import { PureComponent } from 'react';
import Modal from 'react-modal';
import { connect } from 'react-redux';
import classNames from 'classnames';

import { LOGIN_URL } from 'constants/Layout';
import { handleError } from './nsoSlice';

import { getTransChanges, logout } from 'api';
import { unsubscribeAll } from 'api/comet';


const mapDispatchToProps = {
  handleError,
  unsubscribeAll: unsubscribeAll,
  doLogout: logout.initiate,
  getTransChanges: getTransChanges.initiate
};

class UserMenu extends PureComponent {
  constructor(props) {
    super(props);
    this.state = {
      menuOpen: false,
      logoutDialogOpen: false,
      transactionChanges: 0
    };
  }

  openMenu = () => {
    this.setState({ menuOpen: true });
  };

  closeMenu = () => {
    this.setState({ menuOpen: false });
  };

  openLogoutDialog = () => {
    this.setState({ logoutDialogOpen: true });
  };

  closeLogoutDialog = () => {
    this.setState({ logoutDialogOpen: false });
  };

  logout = async () => {
    const { handleError, doLogout, unsubscribeAll } = this.props;
    try {
      await unsubscribeAll();
      await doLogout();
      window.location.assign(LOGIN_URL);
    } catch(error) {
      handleError('Error logging out', error);
    }
  };

  safeLogout = async () => {
    const { getTransChanges, hasWriteTransaction } = this.props;
    this.closeMenu();
    if ( hasWriteTransaction ) {
      this.openLogoutDialog();
      const transChangesQuery = getTransChanges();
      this.setState({ transactionChanges: (await transChangesQuery).data });
      transChangesQuery.unsubscribe();
    } else {
      this.logout();
    }
  };

  render() {
    console.debug('UserMenu Render');
    const { menuOpen, logoutDialogOpen, transactionChanges } = this.state;
    const { user } = this.props;
    return (
      <div className="nso-user-menu">
        <button
          className="btn-reset nso-user-menu__user"
          onClick={this.openMenu}
        >{user} ▾</button>
        <div className={classNames('nso-user-menu__popup', {
          'nso-user-menu__popup--open': menuOpen
        })}>
          <div className="nso-user-menu__overlay" onClick={this.closeMenu}/>
          <div className="nso-user-menu__arrow nso-user-menu__arrow--shadow"/>
          <div className="nso-user-menu__popup-inner">
            <a
              className="btn nso-user-menu__logout"
              onClick={this.safeLogout}
            >Log Out</a>
          </div>
          <div className="nso-user-menu__arrow"/>
        </div>
        <Modal
          isOpen={logoutDialogOpen}
          contentLabel="Logout Warning"
          onRequestClose={this.closeLogoutDialog}
          className="nso-modal__content"
          overlayClassName="nso-modal__overlay"
        >
          <div className="nso-modal__title">Sure you want to log out?</div>
          <div className="nso-modal__body">{transactionChanges} change{
            transactionChanges !== 1 && 's'} will be lost.</div>
          <div className="nso-modal__footer">
            <button
              className="nso-btn nso-btn--alt"
              onClick={this.closeLogoutDialog}
            >Cancel</button>
            <div className="nso-btn__spacer"/>
            <button className="nso-btn" onClick={this.logout}>Confirm</button>
          </div>
        </Modal>
      </div>
    );
  }
}

export default connect(undefined, mapDispatchToProps)(UserMenu);
