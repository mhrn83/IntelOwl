import React from "react";
import {
  Offcanvas,
  OffcanvasHeader,
  OffcanvasBody,
  Badge,
  Alert,
} from "reactstrap";

import { useChatStore, ConnectionState } from "../../stores/useChatStore";
import { useChatWebSocket } from "./useChatWebSocket";
import { ChatMessageList } from "./ChatMessageList";
import { ChatComposer } from "./ChatComposer";

// Connection-state badge shown in the drawer header.
const CONNECTION_BADGE = {
  [ConnectionState.IDLE]: { color: "secondary", label: "Idle" },
  [ConnectionState.CONNECTING]: { color: "warning", label: "Connecting" },
  [ConnectionState.CONNECTED]: { color: "success", label: "Connected" },
  [ConnectionState.RECONNECTING]: { color: "warning", label: "Reconnecting" },
  [ConnectionState.CLOSED]: { color: "danger", label: "Disconnected" },
};

/**
 * The chat drawer. Mounted once, globally (AppMain Layout), so it overlays every authenticated
 * page and survives open/close; the WebSocket lives in useChatWebSocket, which lazily connects the
 * first time the drawer opens. `backdrop={false}` keeps the rest of the app usable while open.
 */
export function ChatPanel() {
  const isOpen = useChatStore((state) => state.isOpen);
  const close = useChatStore((state) => state.close);
  const connectionState = useChatStore((state) => state.connectionState);
  const error = useChatStore((state) => state.error);
  const { sendMessage } = useChatWebSocket();

  const badge =
    CONNECTION_BADGE[connectionState] ?? CONNECTION_BADGE[ConnectionState.IDLE];

  return (
    <Offcanvas
      direction="end"
      isOpen={isOpen}
      toggle={close}
      backdrop={false}
      scrollable
      id="chat-panel"
    >
      <OffcanvasHeader toggle={close}>
        Assistant
        <Badge color={badge.color} className="ms-2">
          {badge.label}
        </Badge>
      </OffcanvasHeader>
      <OffcanvasBody className="d-flex flex-column p-0">
        {error && (
          <Alert color="danger" className="m-2">
            {error}
          </Alert>
        )}
        <ChatMessageList />
        <ChatComposer onSend={sendMessage} />
      </OffcanvasBody>
    </Offcanvas>
  );
}
