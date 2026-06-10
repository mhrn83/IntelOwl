import React from "react";
import "@testing-library/jest-dom";
import { render, screen, act } from "@testing-library/react";

import { ChatPanel } from "../../../src/components/chat/ChatPanel";
import {
  useChatStore,
  ConnectionState,
  MessageRole,
} from "../../../src/stores/useChatStore";

// No-op WebSocket so the lazily-connecting hook does not touch the network in jsdom. It opens on
// the next tick so the hook transitions CONNECTING -> CONNECTED like a real socket.
class StubWebSocket {
  constructor() {
    this.readyState = StubWebSocket.OPEN;
    setTimeout(() => {
      if (this.onopen) this.onopen({});
    }, 0);
  }

  // eslint-disable-next-line class-methods-use-this
  send() {}

  // eslint-disable-next-line class-methods-use-this
  close() {}
}
StubWebSocket.OPEN = 1;

const baseState = {
  isOpen: true,
  sessionId: null,
  messages: [],
  streamingText: "",
  currentTool: null,
  isStreaming: false,
  connectionState: ConnectionState.CONNECTED,
  error: null,
};

describe("ChatPanel", () => {
  beforeAll(() => {
    window.HTMLElement.prototype.scrollIntoView = jest.fn();
  });

  beforeEach(() => {
    global.WebSocket = StubWebSocket;
    useChatStore.setState(baseState);
  });

  test("renders the composer and the connection badge when open", async () => {
    render(<ChatPanel />);
    expect(screen.getByPlaceholderText(/Ask about/i)).toBeInTheDocument();
    // the hook flips CONNECTING -> CONNECTED once the (stub) socket opens
    expect(await screen.findByText("Connected")).toBeInTheDocument();
  });

  test("renders the conversation from store state", () => {
    useChatStore.setState({
      messages: [
        { role: MessageRole.USER, content: "show my jobs" },
        { id: 1, role: MessageRole.ASSISTANT, content: "Here they are" },
      ],
    });
    render(<ChatPanel />);
    expect(screen.getByText("show my jobs")).toBeInTheDocument();
    expect(screen.getByText("Here they are")).toBeInTheDocument();
  });

  test("surfaces an error banner", () => {
    render(<ChatPanel />);
    act(() => {
      useChatStore
        .getState()
        .applyError(
          "The assistant is currently unavailable. Please try again.",
        );
    });
    expect(screen.getByText(/currently unavailable/i)).toBeInTheDocument();
  });
});
