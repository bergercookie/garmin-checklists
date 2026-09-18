# Checklists

A Garmin watch app for checklists — dive kit, pre-flight, packing — backed by a
small self-hosted bridge that pulls them from Vikunja, Trilium Notes, or its
own built-in editor.

Works on **fenix 7** and **Descent G2**.

```{image} images/fenix7-index.png
:alt: The checklist index on a fenix 7
:width: 240px
```
```{image} images/fenix7-checklist-ticked.png
:alt: A checklist with an item ticked
:width: 240px
```

## Who this is for

You, if you run your own server and want your checklists on your wrist.

**You will get on with this if you** already self-host a few things, keep a
reverse proxy with real certificates, and are happy editing a compose file and
reading a log. Setup is about fifteen minutes.

**Look elsewhere if you** want an app-store download with an account and a
cloud. There is no hosted service — no one runs this for you, and your provider
credentials sit in a file on your own disk.

**You need:** a machine that stays on, a domain with HTTPS in front of it
(Connect IQ refuses plain HTTP), and either Vikunja or a willingness to keep
your checklists in the bridge itself.

## Two rules

1. **Checklists flow one way.** The bridge serves templates. Ticks stay on the
   watch and are never written back.
2. **A sync replaces everything and clears every tick.** Items always arrive
   unticked. That is also how you reset a template for its next use.

## Start here

```{toctree}
:maxdepth: 1

getting-started
bridge
install-on-watch
watch-app
vikunja
trilium
providers
architecture
testing
releasing
```
