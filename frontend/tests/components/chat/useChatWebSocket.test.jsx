import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";

import { useChatWebSocket } from "../../../src/components/chat/useChatWebSocket";
import {
  useChatStore,
  ConnectionState,
} from "../../../src/stores/useChatStore";

// Minimal controllable WebSocket double (jsdom has none). Tests drive the server side via the
// mock* helpers and inspect what the hook sent.
class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = FakeWebSocket.CONNECTING;
    this.sent = [];
    FakeWebSocket.instances.push(this);
  }

  send(data) {
    this.sent.push(JSON.parse(data));
  }

  close(code) {
    this.readyState = FakeWebSocket.CLOSED;
    if (this.onclose) this.onclose({ code: code ?? 1000 });
  }

  // --- test helpers ---
  mockOpen() {
    this.readyState = FakeWebSocket.OPEN;
    if (this.onopen) this.onopen({});
  }

  mockMessage(payload) {
    if (this.onmessage) this.onmessage({ data: JSON.stringify(payload) });
  }

  mockServerClose(code) {
    this.readyState = FakeWebSocket.CLOSED;
    if (this.onclose) this.onclose({ code });
  }
}
FakeWebSocket.OPEN = 1;
FakeWebSocket.CONNECTING = 0;
FakeWebSocket.CLOSED = 3;
FakeWebSocket.instances = [];

function Harness() {
  const { sendMessage } = useChatWebSocket();
  return (
    <button type="button" onClick={() => sendMessage("hello")}>
      send
    </button>
  );
}

const lastSocket = () =>
  FakeWebSocket.instances[FakeWebSocket.instances.length - 1];

const initialState = {
  isOpen: false,
  sessionId: null,
  messages: [],
  streamingText: "",
  currentTool: null,
  isStreaming: false,
  connectionState: ConnectionState.IDLE,
  error: null,
};

describe("useChatWebSocket", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    FakeWebSocket.instances = [];
    global.WebSocket = FakeWebSocket;
    useChatStore.setState(initialState);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // open the drawer so the hook lazily connects, then complete the handshake
  function connectAndOpen() {
    render(<Harness />);
    act(() => {
      useChatStore.getState().open();
    });
    act(() => {
      lastSocket().mockOpen();
    });
  }

  test("connects lazily on open and reaches CONNECTED", () => {
    render(<Harness />);
    expect(FakeWebSocket.instances).toHaveLength(0); // not connected while closed
    act(() => {
      useChatStore.getState().open();
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(lastSocket().url).toContain("/ws/chat/?context_url=");
    act(() => {
      lastSocket().mockOpen();
    });
    expect(useChatStore.getState().connectionState).toBe(
      ConnectionState.CONNECTED,
    );
  });

  test("sendMessage emits {message, session_id} and binds the session on ack", () => {
    connectAndOpen();
    act(() => {
      fireEvent.click(screen.getByText("send"));
    });
    expect(lastSocket().sent).toEqual([{ message: "hello", session_id: null }]);
    expect(useChatStore.getState().messages).toHaveLength(1);

    act(() => {
      lastSocket().mockMessage({ type: "ack", session_id: 5 });
    });
    expect(useChatStore.getState().sessionId).toBe(5);
  });

  test("streams start -> token -> end for the active session", () => {
    connectAndOpen();
    act(() => {
      lastSocket().mockMessage({ type: "ack", session_id: 5 });
      lastSocket().mockMessage({ type: "start", session_id: 5 });
      lastSocket().mockMessage({
        type: "status",
        session_id: 5,
        tool: "search_jobs",
      });
      lastSocket().mockMessage({
        type: "token",
        session_id: 5,
        content: "Hi ",
      });
      lastSocket().mockMessage({
        type: "token",
        session_id: 5,
        content: "you",
      });
    });
    expect(useChatStore.getState().streamingText).toBe("Hi you");
    expect(useChatStore.getState().currentTool).toBe("search_jobs");

    act(() => {
      lastSocket().mockMessage({
        type: "end",
        session_id: 5,
        message_id: 9,
        content: "Hi you!",
      });
    });
    const state = useChatStore.getState();
    expect(state.messages.at(-1)).toEqual({
      id: 9,
      role: "assistant",
      content: "Hi you!",
    });
    expect(state.isStreaming).toBe(false);
  });

  test("ignores streaming frames for another session (multi-tab demux)", () => {
    connectAndOpen();
    act(() => {
      lastSocket().mockMessage({ type: "ack", session_id: 5 });
      lastSocket().mockMessage({ type: "start", session_id: 5 });
      lastSocket().mockMessage({
        type: "token",
        session_id: 999,
        content: "X",
      });
    });
    expect(useChatStore.getState().streamingText).toBe("");
  });

  test("surfaces a null-session error but ignores another session's error", () => {
    connectAndOpen();
    act(() => {
      useChatStore.setState({ sessionId: 5 });
      lastSocket().mockMessage({
        type: "error",
        session_id: 999,
        detail: "other tab",
      });
    });
    expect(useChatStore.getState().error).toBeNull();

    act(() => {
      lastSocket().mockMessage({
        type: "error",
        session_id: null,
        detail: "Invalid message payload.",
      });
    });
    expect(useChatStore.getState().error).toBe("Invalid message payload.");
  });

  test("post-ack watchdog fires when no start follows the ack", () => {
    connectAndOpen();
    act(() => {
      lastSocket().mockMessage({ type: "ack", session_id: 5 });
    });
    act(() => {
      jest.advanceTimersByTime(20000);
    });
    const state = useChatStore.getState();
    expect(state.error).toMatch(/unavailable/i);
    expect(state.isStreaming).toBe(false);
  });

  test("post-ack watchdog is cleared once start arrives", () => {
    connectAndOpen();
    act(() => {
      lastSocket().mockMessage({ type: "ack", session_id: 5 });
      lastSocket().mockMessage({ type: "start", session_id: 5 });
    });
    act(() => {
      jest.advanceTimersByTime(20000);
    });
    expect(useChatStore.getState().error).toBeNull();
  });

  test("max-turn watchdog fires when no end follows start", () => {
    connectAndOpen();
    act(() => {
      lastSocket().mockMessage({ type: "ack", session_id: 5 });
      lastSocket().mockMessage({ type: "start", session_id: 5 });
    });
    act(() => {
      jest.advanceTimersByTime(310000);
    });
    const state = useChatStore.getState();
    expect(state.error).toMatch(/too long/i);
    expect(state.isStreaming).toBe(false);
  });

  test("reconnects with backoff on an unexpected close", () => {
    connectAndOpen();
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => {
      lastSocket().mockServerClose(1006); // abnormal closure
    });
    expect(useChatStore.getState().connectionState).toBe(
      ConnectionState.RECONNECTING,
    );
    act(() => {
      jest.advanceTimersByTime(1000); // first backoff step
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  test("keeps the max-turn watchdog armed across a mid-turn reconnect", () => {
    connectAndOpen();
    act(() => {
      lastSocket().mockMessage({ type: "ack", session_id: 5 });
      lastSocket().mockMessage({ type: "start", session_id: 5 });
    });
    expect(useChatStore.getState().isStreaming).toBe(true);

    // socket drops mid-turn, then reconnects; the in-flight turn's `end` is lost in the dead window
    act(() => {
      lastSocket().mockServerClose(1006);
    });
    act(() => {
      jest.advanceTimersByTime(1000); // reconnect backoff
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
    act(() => {
      lastSocket().mockOpen();
    });

    // the watchdog survived the drop and still unlocks the composer instead of hanging on isStreaming
    act(() => {
      jest.advanceTimersByTime(310000);
    });
    const state = useChatStore.getState();
    expect(state.error).toMatch(/too long/i);
    expect(state.isStreaming).toBe(false);
  });

  test("does not reconnect on a clean close", () => {
    connectAndOpen();
    act(() => {
      lastSocket().mockServerClose(1000); // normal closure
    });
    expect(useChatStore.getState().connectionState).toBe(
      ConnectionState.CLOSED,
    );
    act(() => {
      jest.advanceTimersByTime(60000);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
