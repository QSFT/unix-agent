import logging
from dcm.agent import longrunners, utils
import Queue
import threading

import dcm.agent.jobs as jobs
import dcm.eventlog.tracer as tracer
import dcm.agent.parent_receive_q as parent_receive_q


_g_logger = logging.getLogger(__name__)


class WorkLoad(object):
    def __init__(self, request_id, payload, items_map):
        self.request_id = request_id
        self.payload = payload
        self.items_map = items_map
        self.quit = False


class WorkReply(object):
    def __init__(self, request_id, reply_doc):
        self.request_id = request_id
        self.reply_doc = reply_doc


def _run_plugin(conf, items_map, request_id, command, arguments):
    try:
        plugin = jobs.load_plugin(
            conf,
            items_map,
            request_id,
            command,
            arguments)

        utils.log_to_dcm(
            logging.INFO,
            "Starting job for command %s %s" % (command, request_id))
        reply_doc = plugin.run()
        utils.log_to_dcm(
            logging.INFO,
            "Completed successfully job %s %s" % (command, request_id))
    except Exception as ex:
        _g_logger.exception(
            "Worker %s thread had a top level error when "
            "running job %s : %s"
            % (threading.current_thread().getName(), request_id, ex.message))
        utils.log_to_dcm(
            logging.ERROR,
            "A top level error occurred handling %s %s" % (command,
                                                           request_id))
        reply_doc = {
            'Exception': ex.message,
            'return_code': 1}
    finally:
        _g_logger.info("Task done job " + request_id)
    return reply_doc


class Worker(threading.Thread):

    def __init__(self, conf, worker_queue, reply_q):
        super(Worker, self).__init__()
        self.worker_queue = worker_queue
        self.reply_q = reply_q
        self._exit = threading.Event()
        self._conf = conf
        self._is_done = False

    # It should be safe to call done without a lock
    def done(self):
        _g_logger.debug("done() called on worker %s .." % self.getName())
        self._is_done = True
        self._exit.set()

    def run(self):
        try:
            utils.log_to_dcm(
                logging.INFO, "Worker %s thread starting." % self.getName())

            done = False
            while not done:
                try:
                    workload = self.worker_queue.get()
                    if workload is None:
                        continue
                    if workload.quit:
                        done = True
                        self.worker_queue.task_done()
                        continue

                    # setup message logging
                    with tracer.RequestTracer(workload.request_id):

                        reply_doc = _run_plugin(self._conf,
                                                workload.items_map,
                                                workload.request_id,
                                                workload.payload["command"],
                                                workload.payload["arguments"])
                        self.worker_queue.task_done()

                        _g_logger.debug(
                            "Adding the reply document to the reply "
                            "queue " + str(reply_doc))

                        work_reply = WorkReply(workload.request_id, reply_doc)
                        self.reply_q.put(work_reply)
                        utils.log_to_dcm(logging.INFO, "Reply message sent")
                except Queue.Empty:
                    pass
                except:
                    _g_logger.exception(
                        "Something went wrong processing the queue")
                    raise
        finally:
            _g_logger.info("Worker %s thread ending." % self.getName())


# TODO verify stopping behavior
class Dispatcher(object):

    def __init__(self, conf):
        self._conf = conf
        self.workers = []
        self.worker_q = Queue.Queue()
        self.reply_q = parent_receive_q.get_master_receive_queue(
            self, str(self))
        self._long_runner = longrunners.LongRunner(conf)
        self.request_listener = None

    def start_workers(self, request_listener):
        utils.log_to_dcm(
            logging.INFO, "Starting %d workers." % self._conf.workers_count)
        self.request_listener = request_listener
        for i in range(self._conf.workers_count):
            worker = Worker(self._conf, self.worker_q, self.reply_q)
            _g_logger.debug("Starting worker %d : %s" % (i, str(worker)))
            worker.start()
            self.workers.append(worker)

    def stop(self):
        utils.log_to_dcm(logging.INFO, "Stopping workers.")

        for w in self.workers:
            workload = WorkLoad(None, None, None)
            workload.quit = True
            self.worker_q.put(workload)

        for w in self.workers:
            _g_logger.debug("Stopping worker %s" % str(w))
            w.done()
            w.join()
            _g_logger.debug("Worker %s is done" % str(w))
        _g_logger.info("Shutting down the long runner.")
        self._long_runner.shutdown()
        _g_logger.info("Flushing the work queue.")
        while not self.worker_q.empty():
            workload = self.worker_q.get()
            #req_reply.shutdown()
        _g_logger.info("The dispatcher is closed.")

    def incoming_request(self, reply_obj):
        payload = reply_obj.get_message_payload()
        _g_logger.debug("Incoming request %s" % str(payload))
        request_id = reply_obj.get_request_id()
        _g_logger.info("Creating a request ID %s" % request_id)

        items_map = jobs.parse_plugin_doc(self._conf, payload["command"])

        utils.log_to_dcm(
            logging.INFO,
            "Incoming request for command %s" % payload["command"])

        immediate = "immediate" in items_map
        long_runner = "longer_runner" in items_map
        if "longer_runner" in payload:
            long_runner = bool(payload["longer_runner"])

        # we ack first.  This will write it to the persistent store before
        # sending the message so the agent will have it for restarts
        reply_obj.ack(None, None, None)
        if long_runner:
            dj = self._long_runner.start_new_job(
                self._conf,
                request_id,
                items_map,
                payload["command"],
                payload["arguments"])
            payload_doc = dj.get_message_payload()
            reply_doc = {
                "return_code": 0,
                "reply_type": "job_description",
                "reply_object": payload_doc
            }
            wr = WorkReply(request_id, reply_doc)
            self.reply_q.put(wr)
        elif immediate:
            items_map["long_runner"] = self._long_runner
            reply_doc = _run_plugin(self._conf,
                                    items_map,
                                    request_id,
                                    payload["command"],
                                    payload["arguments"])
            wr = WorkReply(request_id, reply_doc)
            self.reply_q.put(wr)
        else:
            workload = WorkLoad(request_id, payload, items_map)
            self.worker_q.put(workload)

        _g_logger.debug(
            "The request %s has been set to send an ACK" % request_id)

    def incoming_parent_q_message(self, work_reply):
        self.request_listener.reply(work_reply.request_id,
                                    work_reply.reply_doc)