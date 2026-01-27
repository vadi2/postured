/**
 * Postured Overlay GNOME Shell Extension
 *
 * Creates fullscreen dimming overlays controlled via D-Bus.
 * Used by postured posture monitor to provide visual feedback.
 */

import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const DBUS_INTERFACE = `
<node>
  <interface name="org.postured.Overlay1">
    <method name="SetOpacity">
      <arg type="d" direction="in" name="opacity"/>
    </method>
    <method name="Quit"/>
    <property name="Available" type="b" access="read"/>
  </interface>
</node>`;

const MAX_OPACITY = 0.85;

export default class PosturedOverlayExtension {
    constructor() {
        this._overlays = [];
        this._dbusId = null;
        this._dbusRegistrationId = null;
        this._dbusConnection = null;
        this._monitorsChangedId = null;
        this._currentOpacity = 0;
    }

    enable() {
        this._createOverlays();
        this._exportDBus();

        // Handle monitor hotplug
        this._monitorsChangedId = Main.layoutManager.connect(
            'monitors-changed',
            () => this._recreateOverlays()
        );
    }

    disable() {
        // Clean up monitor listener
        if (this._monitorsChangedId) {
            Main.layoutManager.disconnect(this._monitorsChangedId);
            this._monitorsChangedId = null;
        }

        // Unexport D-Bus
        if (this._dbusRegistrationId && this._dbusConnection) {
            this._dbusConnection.unregister_object(this._dbusRegistrationId);
            this._dbusRegistrationId = null;
        }
        if (this._dbusId) {
            Gio.bus_unown_name(this._dbusId);
            this._dbusId = null;
        }
        this._dbusConnection = null;

        // Remove overlays
        this._destroyOverlays();
    }

    _createOverlays() {
        const monitors = Main.layoutManager.monitors;

        for (let i = 0; i < monitors.length; i++) {
            const monitor = monitors[i];

            const overlay = new St.Bin({
                style: 'background-color: rgba(0,0,0,1);',
                reactive: false,
                can_focus: false,
                opacity: 0,
            });

            overlay.set_position(monitor.x, monitor.y);
            overlay.set_size(monitor.width, monitor.height);

            // addTopChrome places it above windows but below panel
            Main.layoutManager.addTopChrome(overlay);
            this._overlays.push(overlay);
        }
    }

    _destroyOverlays() {
        for (const overlay of this._overlays) {
            Main.layoutManager.removeChrome(overlay);
            overlay.destroy();
        }
        this._overlays = [];
    }

    _recreateOverlays() {
        const savedOpacity = this._currentOpacity;
        this._destroyOverlays();
        this._createOverlays();
        this._setOpacity(savedOpacity);
    }

    _setOpacity(opacity) {
        // Clamp to 0-1 range
        opacity = Math.max(0, Math.min(1, opacity));
        this._currentOpacity = opacity;

        // Convert to 0-255 range with MAX_OPACITY limit
        const gnomeOpacity = Math.round(opacity * 255 * MAX_OPACITY);

        for (const overlay of this._overlays) {
            overlay.set_opacity(gnomeOpacity);
        }
    }

    _exportDBus() {
        const nodeInfo = Gio.DBusNodeInfo.new_for_xml(DBUS_INTERFACE);
        const interfaceInfo = nodeInfo.interfaces[0];

        this._dbusId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            'org.postured.Overlay',
            Gio.BusNameOwnerFlags.NONE,
            (connection, name) => {
                // Bus acquired
                this._dbusConnection = connection;
                this._dbusRegistrationId = connection.register_object(
                    '/org/postured/Overlay',
                    interfaceInfo,
                    (connection, sender, path, iface, method, params, invocation) => {
                        this._handleMethodCall(method, params, invocation);
                    },
                    (connection, sender, path, iface, property) => {
                        return this._handleGetProperty(property);
                    },
                    null // No set handler needed
                );
            },
            null, // Name acquired callback (not needed)
            null  // Name lost callback (not needed)
        );
    }

    _handleMethodCall(method, params, invocation) {
        try {
            if (method === 'SetOpacity') {
                const [opacity] = params.deep_unpack();
                this._setOpacity(opacity);
                invocation.return_value(null);
            } else if (method === 'Quit') {
                // Reset opacity to 0 (effectively hiding overlays)
                this._setOpacity(0);
                invocation.return_value(null);
            } else {
                invocation.return_error_literal(
                    Gio.DBusError,
                    Gio.DBusError.UNKNOWN_METHOD,
                    `Unknown method: ${method}`
                );
            }
        } catch (e) {
            invocation.return_error_literal(
                Gio.DBusError,
                Gio.DBusError.FAILED,
                e.message
            );
        }
    }

    _handleGetProperty(property) {
        if (property === 'Available') {
            return new GLib.Variant('b', true);
        }
        return null;
    }
}
