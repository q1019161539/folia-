'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const core=fs.readFileSync(process.argv[2],'utf8');
const start=core.indexOf('onEnd: async (data) => {');
const callback=core.slice(start+'onEnd: '.length,core.indexOf('// 稿件检查',start))+'}';
let captured;
const scope={extraOptions:{foliaCollectionTracking:true},formattedOptions:{seasonId:789,sectionId:321,title:'song'},
 uid:1,pTask:{taskId:'test-task',taskList:[{status:'completed',completedPart:{cid:456}}]},
 foliaSeasonJobs:{enqueue:input=>{captured=input;}},client:{platform:{getArchive:()=>{throw Error('unexpected archive query');}}},
 logObj:{error:()=>{throw Error('unexpected callback error');}}};
vm.createContext(scope);
vm.runInContext('callback='+callback,scope);
(async()=>{await scope.callback({aid:123,bvid:'BVtest'});assert.equal(captured.cid,456);assert.equal(captured.aid,123);assert.equal(captured.taskId,'test-task');console.log('ACTUAL_BUNDLE_CALLBACK_TEST_OK');})().catch(e=>{console.error(e);process.exitCode=1;});
