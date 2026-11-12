#!/usr/bin/perl
# Masks stream keys, tokens, passwords and the like in a log stream, line by line.
$| = 1;
while (<STDIN>) {
    s#(rtmps?://[^/\s"]+/[^/\s"]+/)[^\s"]+#$1<masked>#g;
    s#eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_.-]+#<jwt>#g;
    s#((?:token|secret|passw(?:or)?d|pwd|authorization|bearer|license|app_?key|api_?key|stream_?key|sign(?:ature)?|credential|psk)\w*["']?\s*[=:]\s*["']?)[^\s,"'&\}]+#$1<masked>#gi;
    print;
}
