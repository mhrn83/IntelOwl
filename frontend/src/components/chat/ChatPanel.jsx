import React from "react";
import {
  Offcanvas,
  OffcanvasHeader,
  OffcanvasBody,
  Badge,
  Alert,
  Button,
} from "reactstrap";
import { IoListOutline, IoArrowBack } from "react-icons/io5";

import { useChatStore, ConnectionState } from "../../stores/useChatStore";
import { useChatWebSocket } from "./useChatWebSocket";
import { ChatMessageList } from "./ChatMessageList";
import { ChatComposer } from "./ChatComposer";
import { ChatSessionList } from "./ChatSessionList";

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

  // Master-detail mode: "conversation" (messages + composer) or "sessions" (the session list).
  // Local state — purely presentational and not shared with the distant header, unlike `isOpen`.
  const [view, setView] = React.useState("conversation");
  // Always reopen the drawer on the conversation view.
  React.useEffect(() => {
    if (!isOpen) setView("conversation");
  }, [isOpen]);

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
        {view === "conversation" ? (
          <Button
            color="link"
            className="p-0 me-2 text-reset"
            aria-label="Show conversations"
            onClick={() => setView("sessions")}
          >
            <IoListOutline />
          </Button>
        ) : (
          <Button
            color="link"
            className="p-0 me-2 text-reset"
            aria-label="Back to conversation"
            onClick={() => setView("conversation")}
          >
            <IoArrowBack />
          </Button>
        )}
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
        {view === "sessions" ? (
          <ChatSessionList onSessionChosen={() => setView("conversation")} />
        ) : (
          <>
            <ChatMessageList />
            <ChatComposer onSend={sendMessage} />
          </>
        )}
      </OffcanvasBody>
    </Offcanvas>
  );
}
